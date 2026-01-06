"""
EasySQL Agent Graph Assembly.

Constructs the LangGraph state machine connecting all nodes.
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from easysql.config import get_settings
from easysql.llm.state import EasySQLState
from easysql.llm.nodes.analyze import analyze_query_node
from easysql.llm.nodes.clarify import clarify_node
from easysql.llm.nodes.retrieve import retrieve_node
from easysql.llm.nodes.build_context import build_context_node
from easysql.llm.nodes.generate_sql import generate_sql_node
from easysql.llm.nodes.validate_sql import validate_sql_node
from easysql.llm.nodes.repair_sql import repair_sql_node


def route_analyze(state: EasySQLState) -> str:
    """Routing logic after analysis.
    
    Routes to 'clarify' if clarification_questions exist, otherwise 'retrieve'.
    """
    questions = state.get("clarification_questions")
    if questions and len(questions) > 0:
        return "clarify"
    return "retrieve"


def route_validate(state: EasySQLState) -> str:
    """Routing logic after validation.
    
    Routes to END if validation passed or max retries exceeded.
    Otherwise routes to 'repair_sql' for error-informed regeneration.
    """
    if state.get("validation_passed"):
        return END
    
    # Check max retries from config
    settings = get_settings()
    max_retries = settings.llm.max_sql_retries
    retry_count = state.get("retry_count", 0)
    
    if retry_count >= max_retries:
        return END
        
    return "repair_sql"


def build_graph():
    """Builds and compiles the EasySQL Agent Graph."""
    
    builder = StateGraph(EasySQLState)
    
    # --- Add Nodes ---
    builder.add_node("analyze", analyze_query_node)
    builder.add_node("clarify", clarify_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("build_context", build_context_node)
    builder.add_node("generate_sql", generate_sql_node)
    builder.add_node("validate_sql", validate_sql_node)
    builder.add_node("repair_sql", repair_sql_node)
    
    # --- Add Edges ---
    
    # Start -> Analyze
    builder.add_edge(START, "analyze")
    
    # Analyze -> Clarify OR Retrieve
    builder.add_conditional_edges(
        "analyze",
        route_analyze,
        {"clarify": "clarify", "retrieve": "retrieve"}
    )
    
    # Clarify -> Retrieve (after user input resumes)
    builder.add_edge("clarify", "retrieve")
    
    # Retrieve -> Build Context -> Generate SQL -> Validate SQL
    builder.add_edge("retrieve", "build_context")
    builder.add_edge("build_context", "generate_sql")
    builder.add_edge("generate_sql", "validate_sql")
    
    # Validate -> End OR Repair SQL
    builder.add_conditional_edges(
        "validate_sql",
        route_validate,
        {END: END, "repair_sql": "repair_sql"}
    )
    
    # Repair SQL -> Validate SQL (retry loop)
    builder.add_edge("repair_sql", "validate_sql")
    
    # Compile with persistence
    # checkpointer needed for HITL (interrupt)
    checkpointer = MemorySaver()
    
    return builder.compile(checkpointer=checkpointer)
