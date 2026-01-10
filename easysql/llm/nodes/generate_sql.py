"""
Generate SQL Node.

Calls LLM to generate SQL based on the constructed context.
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from easysql.config import LLMConfig, get_settings
from easysql.llm.models import get_llm
from easysql.llm.nodes.base import BaseNode, SQLResponse
from easysql.llm.state import EasySQLState


class GenerateSQLNode(BaseNode):
    """Node to generate SQL from context.

    Uses LLM to generate SQL based on schema context.
    """

    def __init__(self, llm: BaseChatModel | None = None, config: LLMConfig | None = None):
        """Initialize the generate SQL node.

        Args:
            llm: Optional pre-configured LLM. If None, will be created from config.
            config: Optional LLM config. If None, will be loaded from settings.
        """
        self._llm = llm
        self._config = config

    @property
    def config(self) -> LLMConfig:
        """Get or lazily load the config."""
        if self._config is None:
            self._config = get_settings().llm
        return self._config

    def _get_llm(self) -> BaseChatModel:
        """Get LLM for SQL generation.

        Always uses the primary 'model' configured for generation tasks.
        The query_mode only controls HITL flow, not model selection.
        """
        if self._llm is not None:
            return self._llm

        # Always use generation model for SQL generation
        return get_llm(self.config, "generation")

    def __call__(self, state: EasySQLState) -> dict:
        """Generate SQL using the configured LLM.

        Args:
            state: Current graph state.

        Returns:
            State updates with generated_sql.
        """
        context = state["context_output"]
        if not context:
            return {"error": "No context available for generation."}

        llm = self._get_llm()

        messages = [
            SystemMessage(content=context["system_prompt"]),
            HumanMessage(content=context["user_prompt"]),
        ]

        try:
            structured_llm = self.get_structured_llm(llm)
            response: SQLResponse = structured_llm.invoke(messages)
            sql = response.sql

            return {
                "generated_sql": sql,
                "validation_passed": False,
                "validation_result": None,
                "retry_count": state.get("retry_count", 0) + 1,
            }
        except Exception as e:
            return {"error": str(e), "generated_sql": None}


# Factory function for backward compatibility
def generate_sql_node(state: EasySQLState) -> dict:
    """Legacy function wrapper for GenerateSQLNode."""
    node = GenerateSQLNode()
    return node(state)
