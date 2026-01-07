"""
LLM Agentic Layer.

Uses LangGraph and MCP for robust SQL generation and execution.

Main components:
- build_graph: Factory function to create the compiled Agent graph
- EasySQLState: TypedDict defining the graph state schema
- get_llm: Factory function to initialize LLM from config
"""

from easysql.llm.agent import build_graph
from easysql.llm.state import EasySQLState, ContextOutputDict, ValidationResultDict
from easysql.llm.models import get_llm, ModelPurpose

__all__ = [
    # Graph
    "build_graph",
    # State
    "EasySQLState",
    "ContextOutputDict",
    "ValidationResultDict",
    # LLM Factory
    "get_llm",
    "ModelPurpose",
]
