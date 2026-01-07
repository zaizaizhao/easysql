"""
LangGraph Nodes Module.

Contains individual processing nodes for the Agent graph.
Each node is a callable that takes EasySQLState and returns state updates.

Main components:
- BaseNode: Abstract base class for all nodes
- analyze_query_node: Analyzes query ambiguity
- clarify_node: HITL clarification via interrupt
- retrieve_node: Schema retrieval wrapper
- build_context_node: Context construction
- generate_sql_node: SQL generation via LLM
- validate_sql_node: SQL syntax validation
- repair_sql_node: Error-informed SQL repair
"""

from easysql.llm.nodes.base import BaseNode
from easysql.llm.nodes.analyze import AnalyzeQueryNode, analyze_query_node
from easysql.llm.nodes.clarify import ClarifyNode, clarify_node
from easysql.llm.nodes.retrieve import RetrieveNode, retrieve_node
from easysql.llm.nodes.build_context import BuildContextNode, build_context_node
from easysql.llm.nodes.generate_sql import GenerateSQLNode, generate_sql_node
from easysql.llm.nodes.validate_sql import ValidateSQLNode, validate_sql_node
from easysql.llm.nodes.repair_sql import RepairSQLNode, repair_sql_node

__all__ = [
    # Base
    "BaseNode",
    # Node Classes (for DI/testing)
    "AnalyzeQueryNode",
    "ClarifyNode",
    "RetrieveNode",
    "BuildContextNode",
    "GenerateSQLNode",
    "ValidateSQLNode",
    "RepairSQLNode",
    # Factory functions (for graph building)
    "analyze_query_node",
    "clarify_node",
    "retrieve_node",
    "build_context_node",
    "generate_sql_node",
    "validate_sql_node",
    "repair_sql_node",
]
