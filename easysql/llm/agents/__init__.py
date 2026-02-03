"""
LangGraph agents registry.

New agents should live under this package to keep responsibilities separated.
"""

from easysql.llm.agents.sql_agent import (
    build_sql_graph,
    close_checkpointer_pool,
    get_langfuse_callbacks,
    setup_checkpointer,
)
from easysql.llm.agents.viz.agent import build_viz_graph
from easysql.llm.agents.viz.schemas import ChartIntent, VizPlan

__all__ = [
    "build_sql_graph",
    "build_viz_graph",
    "close_checkpointer_pool",
    "get_langfuse_callbacks",
    "setup_checkpointer",
    "ChartIntent",
    "VizPlan",
]
