"""
EasySQL Agent Graph Assembly.

Constructs the LangGraph state machine connecting all nodes.

Graph Flow:
- Fast mode: START -> retrieve -> build_context -> retrieve_code -> generate_sql -> validate_sql -> [END | repair_sql]
- Plan mode: START -> retrieve_hint -> analyze -> [clarify] -> retrieve -> build_context -> retrieve_code -> generate_sql -> validate_sql -> [END | repair_sql]
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from easysql.config import get_settings
from easysql.llm.state import EasySQLState
from easysql.llm.nodes.retrieve_hint import retrieve_hint_node
from easysql.llm.nodes.analyze import analyze_query_node
from easysql.llm.nodes.clarify import clarify_node
from easysql.llm.nodes.retrieve import retrieve_node
from easysql.llm.nodes.build_context import build_context_node
from easysql.llm.nodes.retrieve_code import retrieve_code_node
from easysql.llm.nodes.generate_sql import generate_sql_node
from easysql.llm.nodes.validate_sql import validate_sql_node
from easysql.llm.nodes.repair_sql import repair_sql_node


def route_start(state: EasySQLState) -> str:
    """Route at START based on query_mode.

    Fast mode: Skip retrieve_hint and analyze, go directly to retrieve.
    Plan mode: Go to retrieve_hint for schema-aware analysis.
    """
    settings = get_settings()
    if settings.llm.query_mode == "fast":
        return "retrieve"
    return "retrieve_hint"


def route_analyze(state: EasySQLState) -> str:
    """Route after analyze node.

    If clarification questions exist, route to clarify.
    Otherwise, route directly to retrieve.
    """
    questions = state.get("clarification_questions")
    if questions and len(questions) > 0:
        return "clarify"
    return "retrieve"


def route_validate(state: EasySQLState) -> str:
    """Route after validation.

    Routes to END if validation passed or max retries exceeded.
    Otherwise routes to repair_sql for error-informed regeneration.
    """
    if state.get("validation_passed"):
        return END

    settings = get_settings()
    max_retries = settings.llm.max_sql_retries
    retry_count = state.get("retry_count", 0)

    if retry_count >= max_retries:
        return END

    return "repair_sql"


def build_graph():
    """Builds and compiles the EasySQL Agent Graph."""

    builder = StateGraph(EasySQLState)

    builder.add_node("retrieve_hint", retrieve_hint_node)
    builder.add_node("analyze", analyze_query_node)
    builder.add_node("clarify", clarify_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("build_context", build_context_node)
    builder.add_node("retrieve_code", retrieve_code_node)
    builder.add_node("generate_sql", generate_sql_node)
    builder.add_node("validate_sql", validate_sql_node)
    builder.add_node("repair_sql", repair_sql_node)

    builder.add_conditional_edges(
        START, route_start, {"retrieve_hint": "retrieve_hint", "retrieve": "retrieve"}
    )

    builder.add_edge("retrieve_hint", "analyze")

    builder.add_conditional_edges(
        "analyze", route_analyze, {"clarify": "clarify", "retrieve": "retrieve"}
    )

    builder.add_edge("clarify", "retrieve")

    builder.add_edge("retrieve", "build_context")
    builder.add_edge("build_context", "retrieve_code")
    builder.add_edge("retrieve_code", "generate_sql")
    builder.add_edge("generate_sql", "validate_sql")

    builder.add_conditional_edges(
        "validate_sql", route_validate, {END: END, "repair_sql": "repair_sql"}
    )

    builder.add_edge("repair_sql", "validate_sql")

    checkpointer = MemorySaver()

    return builder.compile(checkpointer=checkpointer)
