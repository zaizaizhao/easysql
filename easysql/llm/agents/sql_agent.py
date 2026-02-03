"""
SQL Agent wrapper for the legacy build_graph entrypoint.

This module keeps SQL agent wiring stable while allowing new agents
to live under the easysql.llm.agents package.
"""

from easysql.llm.agent import (
    build_graph as build_sql_graph,
    close_checkpointer_pool,
    get_langfuse_callbacks,
    setup_checkpointer,
)

__all__ = [
    "build_sql_graph",
    "close_checkpointer_pool",
    "get_langfuse_callbacks",
    "setup_checkpointer",
]
