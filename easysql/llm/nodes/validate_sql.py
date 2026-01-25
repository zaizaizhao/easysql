"""
Validate SQL Node.

Validates the generated SQL using the configured Executor (SQLAlchemy).

.. deprecated::
    This module is deprecated when use_agent_mode=True.
    Use sql_agent.SqlAgentNode instead, which handles validation
    internally via tool execution.
"""

import warnings
from typing import TYPE_CHECKING, Any, Optional

from easysql.llm.state import EasySQLState
from easysql.llm.nodes.base import BaseNode
from easysql.llm.tools.base import BaseSqlExecutor
from easysql.llm.tools.factory import create_sql_executor

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.types import StreamWriter


class ValidateSQLNode(BaseNode):
    """Node to validate generated SQL.

    Uses SQL executor to check syntax via EXPLAIN.
    """

    def __init__(self, executor: Optional[BaseSqlExecutor] = None):
        """Initialize the validate SQL node.

        Args:
            executor: Optional pre-configured SQL executor.
                     If None, will be created via factory.
        """
        self._executor = executor

    @property
    def executor(self) -> BaseSqlExecutor:
        """Get or lazily initialize the SQL executor."""
        if self._executor is None:
            self._executor = create_sql_executor()
        return self._executor

    def __call__(
        self,
        state: EasySQLState,
        config: "RunnableConfig | None" = None,
        *,
        writer: "StreamWriter | None" = None,
    ) -> dict[Any, Any]:
        """Validate SQL syntax and execution plan.

        Args:
            state: Current graph state.

        Returns:
            State updates with validation_passed and validation_result.
        """
        sql = state.get("generated_sql")
        db_name = state.get("db_name") or "default"

        if not sql:
            return {"validation_passed": False, "error": "No SQL generated"}

        # We use check_syntax (EXPLAIN) instead of execute for safety
        result = self.executor.check_syntax(sql, db_name)

        if result.success:
            return {
                "validation_passed": True,
                "validation_result": {
                    "valid": True,
                    "details": "Syntax check passed",
                    "error": None,
                },
            }
        else:
            return {
                "validation_passed": False,
                "validation_result": {"valid": False, "details": None, "error": result.error},
                "error": result.error,
            }


# Factory function for backward compatibility
def validate_sql_node(state: EasySQLState) -> dict:
    warnings.warn(
        "validate_sql_node is deprecated when use_agent_mode=True. Use SqlAgentNode.",
        DeprecationWarning,
        stacklevel=2,
    )
    node = ValidateSQLNode()
    return node(state)
