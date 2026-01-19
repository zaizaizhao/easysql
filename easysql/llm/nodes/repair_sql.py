"""
Repair SQL Node.

Uses LLM to repair failed SQL based on error feedback.
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from easysql.config import LLMConfig, get_settings
from easysql.llm.models import get_llm
from easysql.llm.nodes.base import BaseNode, SQLResponse
from easysql.llm.state import EasySQLState

REPAIR_SYSTEM_PROMPT = """你是一个SQL专家。用户的SQL验证失败，请根据错误信息修复SQL。只输出修正后的SQL，不要输出其他内容。"""


class RepairSQLNode(BaseNode):
    """Node to repair failed SQL using error feedback.

    Takes the error message and original SQL from state,
    uses LLM to generate a corrected version.
    """

    def __init__(self, llm: BaseChatModel | None = None, config: LLMConfig | None = None):
        """Initialize the repair SQL node.

        Args:
            llm: Optional pre-configured LLM. If None, will be created from config.
            config: Optional LLM config. If None, will be loaded from settings.
        """
        self._llm = llm
        self._config = config

    @property
    def llm(self) -> BaseChatModel:
        """Get or lazily initialize the LLM.

        Uses the generation model since SQL repair is part of the SQL generation flow.
        """
        if self._llm is None:
            config = self._config or get_settings().llm
            self._llm = get_llm(config, "generation")
        return self._llm

    async def __call__(self, state: EasySQLState) -> dict:
        """Repair failed SQL using error feedback.

        Args:
            state: Current graph state.

        Returns:
            State updates with repaired generated_sql.
        """
        error = state.get("error")
        original_sql = state.get("generated_sql")
        context = state.get("context_output")

        if not error or not original_sql:
            # Nothing to repair
            return {}

        repair_prompt = f"""原始SQL存在问题，请修复：

错误信息：{error}

原始SQL：
```sql
{original_sql}
```

请基于错误信息修复SQL，只输出修正后的SQL。"""

        messages: list[BaseMessage] = []
        if context and context.get("system_prompt"):
            messages.append(SystemMessage(content=context["system_prompt"]))
        else:
            messages.append(SystemMessage(content=REPAIR_SYSTEM_PROMPT))
        messages.append(HumanMessage(content=repair_prompt))

        try:
            structured_llm = self.get_structured_llm(self.llm)
            response = await structured_llm.ainvoke(messages)
            if not isinstance(response, SQLResponse):
                return {
                    "error": "Invalid response type",
                    "retry_count": state.get("retry_count", 0) + 1,
                }
            sql = response.sql

            return {
                "generated_sql": sql,
                "error": None,
                "retry_count": state.get("retry_count", 0) + 1,
            }
        except Exception as e:
            return {
                "error": f"Repair failed: {e}",
                "retry_count": state.get("retry_count", 0) + 1,
            }


# Factory function for backward compatibility
async def repair_sql_node(state: EasySQLState) -> dict:
    """Legacy function wrapper for RepairSQLNode."""
    node = RepairSQLNode()
    return await node(state)
