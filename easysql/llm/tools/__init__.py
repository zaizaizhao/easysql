"""
SQL Execution Tools Module.

Provides SQL execution strategies for the LLM Agent.
Uses direct SQLAlchemy for database operations.

Main components:
- BaseSqlExecutor: Abstract base class defining executor interface
- SqlAlchemyExecutor: Direct database execution via SQLAlchemy
- create_sql_executor: Factory function for SQLAlchemy executor
- get_agent_tools: Factory for SQL Agent tools
"""

from easysql.llm.tools.agent_tools import (
    ExecuteSqlTool,
    SearchObjectsTool,
    create_agent_tools,
    get_agent_tools,
)
from easysql.llm.tools.base import (
    BaseSqlExecutor,
    DbDialect,
    ExecutionResult,
    SchemaInfoDict,
)
from easysql.llm.tools.factory import create_sql_executor
from easysql.llm.tools.sqlalchemy_executor import SqlAlchemyExecutor

__all__ = [
    # Base classes & types
    "BaseSqlExecutor",
    "ExecutionResult",
    "SchemaInfoDict",
    "DbDialect",
    # Implementations
    "SqlAlchemyExecutor",
    # Factory
    "create_sql_executor",
    # Agent tools
    "ExecuteSqlTool",
    "SearchObjectsTool",
    "create_agent_tools",
    "get_agent_tools",
]
