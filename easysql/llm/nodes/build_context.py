"""
Build Context Node.

Uses ContextBuilder to construct the prompts for SQL generation.
"""

from typing import TYPE_CHECKING, Any, Optional

from easysql.llm.state import EasySQLState
from easysql.llm.nodes.base import BaseNode
from easysql.context.builder import ContextBuilder
from easysql.context.models import ContextInput, FewShotExample
from easysql.context.db_specific_rules import get_db_type_from_config
from easysql.retrieval.schema_retrieval import RetrievalResult

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.types import StreamWriter


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
        self._db_type: str | None = None

    def _get_builder(self, db_name: str | None = None) -> ContextBuilder:
        """Get or lazily initialize the context builder with db_type."""
        if self._builder is not None:
            return self._builder

        # Get database type from config
        db_type = get_db_type_from_config(db_name)
        return ContextBuilder.default(db_type=db_type)

    @property
    def builder(self) -> ContextBuilder:
        """Get or lazily initialize the context builder."""
        if self._builder is None:
            self._builder = ContextBuilder.default()
        return self._builder

    def __call__(
        self,
        state: EasySQLState,
        config: "RunnableConfig | None" = None,
        *,
        writer: "StreamWriter | None" = None,
    ) -> dict[Any, Any]:
        """Construct prompt context from retrieval results.

        Args:
            state: Current graph state.

        Returns:
            State updates with context_output.
        """
        query = state["clarified_query"] or state["raw_query"]
        db_name = state.get("db_name")

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
            stats=retrieval_data.get("stats", {}),
        )

        few_shot_examples: list[FewShotExample] = []
        state_examples = state.get("few_shot_examples")
        if state_examples:
            for ex in state_examples:
                few_shot_examples.append(
                    FewShotExample(
                        question=ex["question"],
                        sql=ex["sql"],
                        tables_used=ex.get("tables_used", []),
                        explanation=ex.get("explanation"),
                    )
                )

        context_input = ContextInput(
            question=query,
            retrieval_result=result_obj,
            db_name=db_name,
            few_shot_examples=few_shot_examples,
        )

        # Use builder with database-specific rules
        builder = self._get_builder(db_name)
        output = builder.build(context_input)

        context_dict = {
            "system_prompt": output.system_prompt,
            "user_prompt": output.user_prompt,
            "total_tokens": output.total_tokens,
        }

        return {
            "context_output": context_dict,
            "cached_context": context_dict,
        }


# Factory function for backward compatibility
def build_context_node(
    state: EasySQLState,
    config: "RunnableConfig | None" = None,
    *,
    writer: "StreamWriter | None" = None,
) -> dict[Any, Any]:
    """Legacy function wrapper for BuildContextNode."""
    node = BuildContextNode()
    return node(state, config, writer=writer)
