"""
SQL Executor Base and Types.

Defines the interface for SQL execution strategies.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, TypedDict


@dataclass
class ExecutionResult:
    """Standardized result from SQL execution."""

    success: bool
    data: list[dict] | None = None
    columns: list[str] | None = None
    error: str | None = None
    row_count: int = 0


class SchemaInfoDict(TypedDict):
    """Structured schema information result."""

    tables: list[str]
    error: str | None


DbDialect = Literal["mysql", "postgresql", "oracle", "sqlserver"]


class BaseSqlExecutor(ABC):
    """Abstract base class for specific SQL execution implementations."""

    @abstractmethod
    def execute_sql(self, sql: str, db_name: str) -> ExecutionResult:
        """Execute SQL query and return results."""
        pass

    @abstractmethod
    def get_schema_info(self, db_name: str) -> SchemaInfoDict:
        """Get schema information (tables/columns) for validation context."""
        pass

    @abstractmethod
    def check_syntax(self, sql: str, db_name: str) -> ExecutionResult:
        """Check SQL syntax strictly without executing (e.g. EXPLAIN)."""
        pass

    @staticmethod
    def get_explain_prefix(dialect: DbDialect) -> str:
        """Get the appropriate EXPLAIN command prefix for each database dialect."""
        prefixes = {
            "mysql": "EXPLAIN",
            "postgresql": "EXPLAIN ANALYZE",
            "oracle": "EXPLAIN PLAN FOR",
            "sqlserver": "SET SHOWPLAN_TEXT ON;",
        }
        return prefixes.get(dialect, "EXPLAIN")
