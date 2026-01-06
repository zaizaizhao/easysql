"""
Build Context Node.

Uses ContextBuilder to construct the prompts for SQL generation.
"""
from typing import Optional

from easysql.llm.state import EasySQLState
from easysql.llm.nodes.base import BaseNode
from easysql.context.builder import ContextBuilder
from easysql.context.models import ContextInput
from easysql.retrieval.schema_retrieval import RetrievalResult


class BuildContextNode(BaseNode):
    """Node to build context from retrieval results.
    
    Wraps ContextBuilder with DI support.
    """
    
    def __init__(self, builder: Optional[ContextBuilder] = None):
        """Initialize the build context node.
        
        Args:
            builder: Optional pre-configured ContextBuilder.
                    If None, will use default builder.
        """
        self._builder = builder
    
    @property
    def builder(self) -> ContextBuilder:
        """Get or lazily initialize the context builder."""
        if self._builder is None:
            self._builder = ContextBuilder.default()
        return self._builder
    
    def __call__(self, state: EasySQLState) -> dict:
        """Construct prompt context from retrieval results.
        
        Args:
            state: Current graph state.
            
        Returns:
            State updates with context_output.
        """
        query = state["clarified_query"] or state["raw_query"]
        
        # Reconstruct RetrievalResult from dict
        retrieval_data = state["retrieval_result"]
        if not retrieval_data:
            return {"error": "No retrieval result found."}
            
        # Manually reconstruct RetrievalResult
        result_obj = RetrievalResult(
            tables=retrieval_data.get("tables", []),
            table_columns=retrieval_data.get("table_columns", {}),
            table_metadata=retrieval_data.get("table_metadata", {}),
            semantic_columns=retrieval_data.get("semantic_columns", []),
            join_paths=retrieval_data.get("join_paths", []),
            stats=retrieval_data.get("stats", {})
        )
        
        context_input = ContextInput(
            question=query,
            retrieval_result=result_obj,
            db_name=state.get("db_name")
        )
        
        output = self.builder.build(context_input)
        
        # Return serializable dict matching ContextOutputDict
        return {
            "context_output": {
                "system_prompt": output.system_prompt,
                "user_prompt": output.user_prompt,
                "total_tokens": output.total_tokens,
            }
        }


# Factory function for backward compatibility
def build_context_node(state: EasySQLState) -> dict:
    """Legacy function wrapper for BuildContextNode."""
    node = BuildContextNode()
    return node(state)
