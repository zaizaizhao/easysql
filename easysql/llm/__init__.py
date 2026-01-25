"""
LLM Agentic Layer.

Uses LangGraph for robust SQL generation and execution.

Main components:
- build_graph: Factory function to create the compiled Agent graph
- EasySQLState: TypedDict defining the graph state schema
- get_llm: Factory function to initialize LLM from config
- SqlAgentNode: Agent for iterative SQL generation (use_agent_mode=True)
"""

from easysql.llm.agent import (
    build_graph,
    close_checkpointer_pool,
    get_langfuse_callbacks,
    setup_checkpointer,
)
from easysql.llm.models import ModelPurpose, get_llm
from easysql.llm.nodes.sql_agent import SqlAgentNode, sql_agent_node
from easysql.llm.state import ContextOutputDict, EasySQLState, ValidationResultDict

__all__ = [
    # Graph
    "build_graph",
    "close_checkpointer_pool",
    "get_langfuse_callbacks",
    "setup_checkpointer",
    # State
    "EasySQLState",
    "ContextOutputDict",
    "ValidationResultDict",
    # LLM Factory
    "get_llm",
    "ModelPurpose",
    # SQL Agent (agent mode)
    "SqlAgentNode",
    "sql_agent_node",
]
