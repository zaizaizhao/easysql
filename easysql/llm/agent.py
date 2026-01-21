"""
EasySQL Agent Graph Assembly.

Constructs the LangGraph state machine connecting all nodes.

Graph Flow:
- Fast mode: START -> retrieve -> build_context -> retrieve_code -> generate_sql -> validate_sql -> [END | repair_sql]
- Plan mode: START -> retrieve_hint -> analyze -> [clarify] -> retrieve -> build_context -> retrieve_code -> generate_sql -> validate_sql -> [END | repair_sql]
"""

from typing import TYPE_CHECKING, Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from easysql.config import get_settings
from easysql.llm.nodes.analyze import analyze_query_node
from easysql.llm.nodes.build_context import build_context_node
from easysql.llm.nodes.clarify import clarify_node
from easysql.llm.nodes.generate_sql import generate_sql_node
from easysql.llm.nodes.repair_sql import repair_sql_node
from easysql.llm.nodes.retrieve import retrieve_node
from easysql.llm.nodes.retrieve_code import retrieve_code_node
from easysql.llm.nodes.retrieve_hint import retrieve_hint_node
from easysql.llm.nodes.shift_detect import shift_detect_node
from easysql.llm.nodes.validate_sql import validate_sql_node
from easysql.llm.state import EasySQLState
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from psycopg_pool import AsyncConnectionPool as AsyncConnectionPoolType

    from easysql.config import Settings

logger = get_logger(__name__)

_checkpointer_pool: "AsyncConnectionPoolType | None" = None


def route_start(state: EasySQLState) -> str:
    """Route at START based on query_mode and follow-up status."""
    if state.get("conversation_history"):
        return "shift_detect"

    settings = get_settings()
    if settings.llm.query_mode == "fast":
        return "retrieve"
    return "retrieve_hint"


def route_shift_detect(state: EasySQLState) -> str:
    """Route after shift detection."""
    if state.get("needs_new_retrieval"):
        settings = get_settings()
        if settings.llm.query_mode == "fast":
            return "retrieve"
        return "retrieve_hint"
    return "generate_sql"


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


def _create_checkpointer() -> BaseCheckpointSaver | Any:
    """Create checkpointer for LangGraph state persistence.

    Uses AsyncPostgresSaver for async graph operations (astream/ainvoke).
    """
    settings = get_settings()

    if not settings.checkpointer.is_postgres():
        logger.info("Using in-memory checkpointer")
        return MemorySaver()

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        global _checkpointer_pool

        logger.info(
            f"Connecting to PostgreSQL checkpointer at {settings.checkpointer.postgres_host}"
        )
        pool = AsyncConnectionPool(
            settings.checkpointer.postgres_uri,
            max_size=10,
            check=AsyncConnectionPool.check_connection,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        _checkpointer_pool = pool
        checkpointer = AsyncPostgresSaver(pool)
        return checkpointer
    except ImportError as e:
        logger.warning(
            f"langgraph-checkpoint-postgres or psycopg_pool not installed: {e}, falling back to memory"
        )
        return MemorySaver()
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}, falling back to memory")
        return MemorySaver()


def _ensure_database_exists(settings: "Settings") -> None:
    """Create the checkpointer database if it doesn't exist."""
    import psycopg

    admin_uri = (
        f"postgresql://{settings.checkpointer.postgres_user}:{settings.checkpointer.postgres_password}"
        f"@{settings.checkpointer.postgres_host}:{settings.checkpointer.postgres_port}/postgres"
    )
    db_name = settings.checkpointer.postgres_database

    with psycopg.connect(admin_uri, autocommit=True) as conn:
        result = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)).fetchone()
        if not result:
            conn.execute(f'CREATE DATABASE "{db_name}"')
            logger.info(f"Created database '{db_name}'")


def setup_checkpointer() -> None:
    """Initialize PostgreSQL checkpointer database and tables if configured.

    Call this during application startup to ensure database/tables exist before handling requests.
    Safe to call multiple times (idempotent).
    """
    settings = get_settings()

    if not settings.checkpointer.is_postgres():
        logger.debug("Checkpointer setup skipped: not using PostgreSQL backend")
        return

    try:
        from langgraph.checkpoint.postgres import PostgresSaver

        logger.info(f"Setting up PostgreSQL checkpointer at {settings.checkpointer.postgres_host}")

        _ensure_database_exists(settings)

        with PostgresSaver.from_conn_string(settings.checkpointer.postgres_uri) as saver:
            saver.setup()
        logger.info("PostgreSQL checkpointer tables ready")
    except ImportError:
        logger.warning("langgraph-checkpoint-postgres not installed, skipping setup")
    except Exception as e:
        logger.error(f"Failed to setup PostgreSQL checkpointer: {e}")
        raise


async def close_checkpointer_pool() -> None:
    """Close the checkpointer connection pool.

    Call during application shutdown to release database connections.
    """
    global _checkpointer_pool
    if _checkpointer_pool is not None:
        logger.info("Closing checkpointer connection pool...")
        await _checkpointer_pool.close()
        _checkpointer_pool = None
        logger.info("Checkpointer connection pool closed")


def get_langfuse_callbacks() -> list[Any]:
    """Get LangFuse callback handlers if configured."""
    settings = get_settings()
    if not settings.langfuse.is_configured():
        return []

    try:
        import os

        from langfuse.langchain import CallbackHandler

        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse.public_key or "")
        os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse.secret_key or "")
        os.environ.setdefault("LANGFUSE_HOST", settings.langfuse.host)

        return [CallbackHandler()]
    except ImportError:
        logger.warning("langfuse package not installed, tracing disabled")
        return []


def build_graph() -> "CompiledStateGraph":
    """Builds and compiles the EasySQL Agent Graph."""

    builder = StateGraph(EasySQLState)

    builder.add_node("shift_detect", shift_detect_node)
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
        START,
        route_start,
        {
            "shift_detect": "shift_detect",
            "retrieve_hint": "retrieve_hint",
            "retrieve": "retrieve",
        },
    )

    builder.add_conditional_edges(
        "shift_detect",
        route_shift_detect,
        {
            "retrieve_hint": "retrieve_hint",
            "retrieve": "retrieve",
            "generate_sql": "generate_sql",
        },
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

    checkpointer = _create_checkpointer()

    compiled = builder.compile(checkpointer=checkpointer)
    return compiled
