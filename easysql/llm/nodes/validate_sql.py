"""
Validate SQL Node.

Validates the generated SQL using the configured Executor (MCP or SQLAlchemy).
"""
from typing import Optional

from easysql.llm.state import EasySQLState
from easysql.llm.nodes.base import BaseNode
from easysql.llm.tools.base import BaseSqlExecutor
from easysql.llm.tools.factory import create_sql_executor


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
    
    def __call__(self, state: EasySQLState) -> dict:
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
                "validation_result": {"valid": True, "details": "Syntax check passed", "error": None}
            }
        else:
            return {
                "validation_passed": False,
                "validation_result": {"valid": False, "details": None, "error": result.error},
                "error": result.error
            }


# Factory function for backward compatibility
def validate_sql_node(state: EasySQLState) -> dict:
    """Legacy function wrapper for ValidateSQLNode."""
    node = ValidateSQLNode()
    return node(state)
