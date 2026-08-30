"""Read-only schema discovery tools for external SQL agents.

This package is deliberately separate from the LangGraph retrieval workflow.
It exposes constrained Milvus and Neo4j capabilities without changing how the
existing workflow retrieves schema context.
"""

from easysql.agent_tools.runtime import get_schema_tool_service
from easysql.agent_tools.service import (
    DatabaseNotConfiguredError,
    SchemaToolService,
)

__all__ = [
    "DatabaseNotConfiguredError",
    "SchemaToolService",
    "get_schema_tool_service",
]
