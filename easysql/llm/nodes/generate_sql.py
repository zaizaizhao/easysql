"""
Generate SQL Node.

Calls LLM to generate SQL based on the constructed context.

.. deprecated::
    This module is deprecated when use_agent_mode=True.
    Use sql_agent.SqlAgentNode instead, which provides iterative
    SQL generation with tool-based validation and repair.
"""

import warnings
from typing import TYPE_CHECKING, Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from easysql.config import LLMConfig, get_settings
from easysql.llm.models import get_llm
from easysql.llm.nodes.base import BaseNode, SQLResponse
from easysql.llm.state import EasySQLState
from easysql.llm.utils.token_manager import get_token_manager

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.types import StreamWriter


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

    async def __call__(
        self,
        state: EasySQLState,
        config: "RunnableConfig | None" = None,
        *,
        writer: "StreamWriter | None" = None,
    ) -> dict[Any, Any]:
        """Generate SQL using the configured LLM."""
        context = state.get("cached_context") or state.get("context_output")
        if not context:
            return {"error": "No context available for generation."}

        llm = self._get_llm()
        messages: list[BaseMessage] = [SystemMessage(content=context["system_prompt"])]

        history = state.get("conversation_history") or []
        if history:
            token_manager = get_token_manager()
            schema_tokens = context.get("total_tokens", 0)
            summary, recent = token_manager.prepare_history(history, schema_tokens)
            history_messages = token_manager.build_history_messages(summary, recent)
            messages.extend(history_messages)

        current_query = state["raw_query"]
        user_prompt = context["user_prompt"]

        history = state.get("conversation_history") or []
        is_follow_up = len(history) > 0
        if is_follow_up and "**用户问题**:" in user_prompt:
            parts = user_prompt.split("**用户问题**:")
            if len(parts) == 2:
                schema_part = parts[0]
                user_prompt = (
                    f"{schema_part}**用户问题**: {current_query}\n\n请生成正确的 SQL 查询语句："
                )

        messages.append(HumanMessage(content=user_prompt))

        try:
            structured_llm = self.get_structured_llm(llm)
            response = await structured_llm.ainvoke(messages)
            if not isinstance(response, SQLResponse):
                return {"error": "Invalid response type", "generated_sql": None}
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
async def generate_sql_node(
    state: EasySQLState,
    config: "RunnableConfig | None" = None,
    *,
    writer: "StreamWriter | None" = None,
) -> dict[Any, Any]:
    warnings.warn(
        "generate_sql_node is deprecated when use_agent_mode=True. Use SqlAgentNode.",
        DeprecationWarning,
        stacklevel=2,
    )
    node = GenerateSQLNode()
    return await node(state, config, writer=writer)
