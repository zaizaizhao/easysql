"""
SQL Execution Tools Module.

Provides SQL execution strategies for the LLM Agent.
Supports MCP (Model Context Protocol) via DBHub and direct SQLAlchemy connections.

Main components:
- BaseSqlExecutor: Abstract base class defining executor interface
- SqlAlchemyExecutor: Direct database execution via SQLAlchemy
- McpExecutor: Execution via DBHub MCP Server
- create_sql_executor: Factory function with MCP-first fallback strategy
"""

from easysql.llm.tools.base import (
    BaseSqlExecutor,
    ExecutionResult,
    SchemaInfoDict,
    DbDialect,
)
from easysql.llm.tools.sqlalchemy_executor import SqlAlchemyExecutor
from easysql.llm.tools.mcp_executor import McpExecutor
from easysql.llm.tools.factory import create_sql_executor

__all__ = [
    # Base classes & types
    "BaseSqlExecutor",
    "ExecutionResult",
    "SchemaInfoDict",
    "DbDialect",
    # Implementations
    "SqlAlchemyExecutor",
    "McpExecutor",
    # Factory
    "create_sql_executor",
]
