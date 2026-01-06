"""
Clarify Node (HITL).

Asks user for clarification if needed using LangGraph interrupt.
"""
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.language_models import BaseChatModel
from langgraph.types import interrupt

from easysql.config import get_settings, LLMConfig
from easysql.llm.state import EasySQLState
from easysql.llm.models import get_llm
from easysql.llm.nodes.base import BaseNode


class ClarifyNode(BaseNode):
    """Node to handle clarification interaction via HITL.
    
    Uses LangGraph interrupt to pause and collect user responses.
    """
    
    def __init__(self, llm: Optional[BaseChatModel] = None, config: Optional[LLMConfig] = None):
        """Initialize the clarify node.
        
        Args:
            llm: Optional pre-configured LLM. If None, will be created from config.
            config: Optional LLM config. If None, will be loaded from settings.
        """
        self._llm = llm
        self._config = config
    
    @property
    def llm(self) -> BaseChatModel:
        """Get or lazily initialize the LLM."""
        if self._llm is None:
            config = self._config or get_settings().llm
            self._llm = get_llm(config, "planning")
        return self._llm
    
    def __call__(self, state: EasySQLState) -> dict:
        """Handle clarification interaction.
        
        1. Get clarification questions from state (set by analyze node).
        2. If yes, interrupt() to ask user.
        3. On resume, combine answer with raw query to form clarified query.
        
        Args:
            state: Current graph state.
            
        Returns:
            State updates with clarified_query.
        """
        # Get questions from state (proper data flow, no message parsing)
        questions = state.get("clarification_questions") or []
        
        if not questions:
            # Should not happen if routing logic is correct, but safety net
            return {"clarified_query": state["raw_query"]}
            
        # Construct question string
        question_text = "\n".join(f"- {q}" for q in questions)
        
        # HITL Interrupt - returns user response when resumed
        user_response = interrupt({
            "type": "clarification",
            "question": f"为了更准确地为您生成SQL，请确认以下信息：\n{question_text}",
            "raw_query": state["raw_query"]
        })
        
        # Use LLM to rewrite query with user's clarification
        rewrite_prompt = f"""基于用户反馈完善查询。

原始问题：{state['raw_query']}
需澄清点：
{question_text}

用户回答：{user_response}

请输出完善后的完整问题（只输出问题文本）："""

        response = self.llm.invoke([HumanMessage(content=rewrite_prompt)])
        
        return {
            "clarified_query": response.content.strip(),
            "clarification_questions": None,  # Clear questions after resolution
            "messages": [
                AIMessage(content=f"已确认：{user_response}\n正在为您生成SQL..."),
                HumanMessage(content=str(user_response))  # Add to history
            ]
        }


# Factory function for backward compatibility
def clarify_node(state: EasySQLState) -> dict:
    """Legacy function wrapper for ClarifyNode."""
    node = ClarifyNode()
    return node(state)
