"""
Analyze Query Node.

Analyzes the user query to determine ambiguity and need for HITL clarification.
"""
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models import BaseChatModel

from easysql.config import get_settings, LLMConfig
from easysql.llm.state import EasySQLState
from easysql.llm.models import get_llm
from easysql.llm.nodes.base import BaseNode


class AnalysisResult(BaseModel):
    """Structured output for query analysis."""
    is_clear: bool = Field(description="Whether the query is clear enough for SQL generation")
    clarification_questions: List[str] = Field(
        default_factory=list,
        description="List of clarifying questions if the query is unclear"
    )
    reasoning: str = Field(description="Reasoning behind the clarity judgment")


ANALYZE_SYSTEM_PROMPT = """你是一个SQL数据分析专家。分析用户问题，判断是否需要进一步澄清以便生成准确的SQL。"""

ANALYZE_USER_PROMPT = """分析以下用户问题：

用户问题：{query}

请判断：
1. 问题是否足够清晰？（如时间范围、聚合粒度、特定条件等是否明确）
2. 是否存在歧义？

如果需要澄清，请列出 1-3 个具体的追问问题。"""


class AnalyzeQueryNode(BaseNode):
    """Node to analyze query ambiguity.
    
    Determines if clarification is needed before SQL generation.
    """
    
    def __init__(self, llm: Optional[BaseChatModel] = None, config: Optional[LLMConfig] = None):
        """Initialize the analyze node.
        
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
    
    @property
    def config(self) -> LLMConfig:
        """Get or lazily load the config."""
        if self._config is None:
            self._config = get_settings().llm
        return self._config
    
    def __call__(self, state: EasySQLState) -> dict:
        """Analyze query and determine if clarification is needed.
        
        Args:
            state: Current graph state containing raw_query.
            
        Returns:
            State updates with clarified_query or clarification_questions.
        """
        # Fast mode: Skip analysis
        if self.config.query_mode == "fast":
            return {
                "clarified_query": state["raw_query"],
                "clarification_questions": None,
            }
            
        # Plan mode: Analyze with structured output
        structured_llm = self.llm.with_structured_output(AnalysisResult)
        
        try:
            result: AnalysisResult = structured_llm.invoke([
                SystemMessage(content=ANALYZE_SYSTEM_PROMPT),
                HumanMessage(content=ANALYZE_USER_PROMPT.format(query=state["raw_query"]))
            ])
            
            is_clear = result.is_clear
            questions = result.clarification_questions
            
            # If model says not clear but gives no questions, assume clear
            if not is_clear and not questions:
                is_clear = True
                
            return {
                "clarified_query": state["raw_query"] if is_clear else None,
                "clarification_questions": questions if not is_clear else None,
            }
        except Exception:
            # Fallback to clear on parsing error
            return {
                "clarified_query": state["raw_query"],
                "clarification_questions": None,
            }


# Factory function for backward compatibility
def analyze_query_node(state: EasySQLState) -> dict:
    """Legacy function wrapper for AnalyzeQueryNode."""
    node = AnalyzeQueryNode()
    return node(state)
