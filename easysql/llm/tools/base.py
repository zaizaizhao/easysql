"""
Base SQL Executor.

Defines the interface for SQL execution strategies (MCP vs SQLAlchemy).
"""
from abc import ABC, abstractmethod
from typing import List, Literal, Optional, TypedDict
from dataclasses import dataclass


@dataclass
class ExecutionResult:
    """Standardized result from SQL execution."""
    success: bool
    data: Optional[List[dict]] = None
    columns: Optional[List[str]] = None
    error: Optional[str] = None
    row_count: int = 0


class SchemaInfoDict(TypedDict):
    """Structured schema information result."""
    tables: List[str]
    error: Optional[str]


# Supported database dialects
DbDialect = Literal["mysql", "postgresql", "oracle", "sqlserver"]


class BaseSqlExecutor(ABC):
    """Abstract base class for specific SQL execution implementations."""
    
    @abstractmethod
    def execute_sql(self, sql: str, db_name: str) -> ExecutionResult:
        """
        Execute SQL query and return results.
        
        Args:
            sql: The SQL query to execute.
            db_name: Target database name.
            
        Returns:
            ExecutionResult containing rows or error.
        """
        pass
    
    @abstractmethod
    def get_schema_info(self, db_name: str) -> SchemaInfoDict:
        """
        Get schema information (tables/columns) for validation context.
        """
        pass
        
    @abstractmethod
    def check_syntax(self, sql: str, db_name: str) -> ExecutionResult:
        """
        Check SQL syntax strictly without executing (e.g. EXPLAIN).
        """
        pass
    
    @staticmethod
    def get_explain_prefix(dialect: DbDialect) -> str:
        """Get the appropriate EXPLAIN command prefix for each database dialect.
        
        Args:
            dialect: Database dialect type.
            
        Returns:
            EXPLAIN prefix string appropriate for the dialect.
        """
        prefixes = {
            "mysql": "EXPLAIN",
            "postgresql": "EXPLAIN ANALYZE",
            "oracle": "EXPLAIN PLAN FOR",
            "sqlserver": "SET SHOWPLAN_TEXT ON;",
        }
        return prefixes.get(dialect, "EXPLAIN")
