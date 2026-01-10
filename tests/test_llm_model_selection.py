
import os
import sys
import unittest
from unittest.mock import patch

# Add parent dir to path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from easysql.config import LLMConfig
from easysql.llm.models import get_llm
from easysql.llm.nodes.analyze import AnalyzeQueryNode
from easysql.llm.nodes.clarify import ClarifyNode
from easysql.llm.nodes.generate_sql import GenerateSQLNode
from easysql.llm.nodes.repair_sql import RepairSQLNode


class TestLLMModelSelection(unittest.TestCase):
    """Verify correct model selection based on purpose and config."""

    def test_get_llm_factory_logic(self):
        """Test get_llm factory function with priority-based model selection."""
        config = LLMConfig(
            openai_llm_model="gpt-4",
            model_planning="gpt-3.5",
            openai_api_key="fake-key"
        )

        # We need to mock _init_openai to avoid actual API warnings/imports if not installed
        with patch("easysql.llm.models._init_openai") as mock_init:
            # 1. Purpose = "generation" -> Should use config.get_model() (gpt-4)
            get_llm(config, "generation")
            mock_init.assert_called_with(config, "gpt-4")

            # 2. Purpose = "planning" -> Should use config.model_planning (gpt-3.5)
            get_llm(config, "planning")
            mock_init.assert_called_with(config, "gpt-3.5")

            # 3. Purpose = "planning" but model_planning is None -> Should fallback to get_model()
            config_no_plan = LLMConfig(
                openai_llm_model="gpt-4",
                model_planning=None,
                openai_api_key="fake-key"
            )
            get_llm(config_no_plan, "planning")
            mock_init.assert_called_with(config_no_plan, "gpt-4")

    def test_provider_priority(self):
        """Test provider priority: Google > Anthropic > OpenAI."""
        # Only OpenAI configured -> should use OpenAI
        config_openai = LLMConfig(
            openai_llm_model="gpt-4o",
            openai_api_key="fake-openai-key"
        )
        self.assertEqual(config_openai.get_provider(), "openai")
        self.assertEqual(config_openai.get_model(), "gpt-4o")

        # Anthropic configured with API key -> should use Anthropic
        config_anthropic = LLMConfig(
            openai_llm_model="gpt-4o",
            anthropic_llm_model="claude-3",
            anthropic_api_key="fake-anthropic-key"
        )
        self.assertEqual(config_anthropic.get_provider(), "anthropic")
        self.assertEqual(config_anthropic.get_model(), "claude-3")

        # Google configured with API key -> should use Google (highest priority)
        config_google = LLMConfig(
            openai_llm_model="gpt-4o",
            anthropic_llm_model="claude-3",
            anthropic_api_key="fake-anthropic-key",
            google_llm_model="gemini-1.5-pro",
            google_api_key="fake-google-key"
        )
        self.assertEqual(config_google.get_provider(), "google_genai")
        self.assertEqual(config_google.get_model(), "gemini-1.5-pro")

    @patch("easysql.llm.nodes.generate_sql.get_llm")
    def test_generate_sql_node_selection(self, mock_get_llm):
        """GenerateSQLNode should ALWAYS use 'generation' purpose."""
        # Case 1: query_mode = 'plan'
        config_plan = LLMConfig(query_mode="plan", openai_llm_model="gpt-4")
        node = GenerateSQLNode(config=config_plan)
        node._get_llm() # Trigger lazy init
        mock_get_llm.assert_called_with(config_plan, "generation")

        # Case 2: query_mode = 'fast'
        config_fast = LLMConfig(query_mode="fast", openai_llm_model="gpt-4")
        node2 = GenerateSQLNode(config=config_fast)
        node2._get_llm()
        mock_get_llm.assert_called_with(config_fast, "generation")

    @patch("easysql.llm.nodes.repair_sql.get_llm")
    def test_repair_sql_node_selection(self, mock_get_llm):
        """RepairSQLNode should use 'generation' purpose."""
        config = LLMConfig(openai_llm_model="gpt-4")
        node = RepairSQLNode(config=config)
        _ = node.llm # Trigger lazy init
        mock_get_llm.assert_called_with(config, "generation")

    @patch("easysql.llm.nodes.analyze.get_llm")
    def test_analyze_node_selection(self, mock_get_llm):
        """AnalyzeQueryNode should use 'planning' purpose."""
        config = LLMConfig(openai_llm_model="gpt-4")
        node = AnalyzeQueryNode(config=config)
        _ = node.llm
        mock_get_llm.assert_called_with(config, "planning")

    @patch("easysql.llm.nodes.clarify.get_llm")
    def test_clarify_node_selection(self, mock_get_llm):
        """ClarifyNode should use 'planning' purpose."""
        config = LLMConfig(openai_llm_model="gpt-4")
        node = ClarifyNode(config=config)
        _ = node.llm
        mock_get_llm.assert_called_with(config, "planning")

if __name__ == '__main__':
    unittest.main()

