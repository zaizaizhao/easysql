"""
Repair SQL Node.

Uses LLM to repair failed SQL based on error feedback.
"""
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models import BaseChatModel

from easysql.config import get_settings, LLMConfig
from easysql.llm.state import EasySQLState
from easysql.llm.models import get_llm
from easysql.llm.nodes.base import BaseNode


REPAIR_SYSTEM_PROMPT = """你是一个SQL专家。用户的SQL验证失败，请根据错误信息修复SQL。只输出修正后的SQL，不要输出其他内容。"""


class RepairSQLNode(BaseNode):
    """Node to repair failed SQL using error feedback.
    
    Takes the error message and original SQL from state,
    uses LLM to generate a corrected version.
    """
    
    def __init__(self, llm: Optional[BaseChatModel] = None, config: Optional[LLMConfig] = None):
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
    
    def __call__(self, state: EasySQLState) -> dict:
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

        messages = []
        if context and context.get("system_prompt"):
            messages.append(SystemMessage(content=context["system_prompt"]))
        else:
            messages.append(SystemMessage(content=REPAIR_SYSTEM_PROMPT))
        messages.append(HumanMessage(content=repair_prompt))
        
        try:
            response = self.llm.invoke(messages)
            sql = self.extract_sql(response.content)
            
            return {
                "generated_sql": sql,
                "error": None,  # Clear error after repair attempt
                "retry_count": state.get("retry_count", 0) + 1,  # Increment to avoid infinite loop
            }
        except Exception as e:
            return {
                "error": f"Repair failed: {e}",
                "retry_count": state.get("retry_count", 0) + 1,  # Increment even on failure
            }


# Factory function for backward compatibility
def repair_sql_node(state: EasySQLState) -> dict:
    """Legacy function wrapper for RepairSQLNode."""
    node = RepairSQLNode()
    return node(state)
