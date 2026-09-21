from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from easysql.config import get_settings
from easysql.infrastructure import (
    DataPlanePoolConfig,
    get_data_plane_engine_registry,
)
from easysql.llm import close_checkpointer_pool, setup_checkpointer
from easysql.utils.logger import get_logger
from easysql_api.routers import (
    chart_router,
    config_router,
    execute_router,
    few_shot_router,
    health_router,
    pipeline_router,
    query_router,
    sessions_router,
)
from easysql_api.routers.agent_tools import router as agent_tools_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("EasySQL API starting up...")

    if not settings.is_session_postgres():
        raise RuntimeError("SESSION_BACKEND must be set to postgres.")

    from easysql_api.deps import get_config_service_dep, set_session_repository
    from easysql_api.infrastructure.db_manager import (
        ControlPlanePoolConfig,
        ensure_control_plane_database_exists,
        get_control_plane_db_manager,
    )
    from easysql_api.infrastructure.persistence.session_repository import (
        SqlAlchemySessionRepository,
    )

    await ensure_control_plane_database_exists(settings.postgres_uri)

    db_manager = get_control_plane_db_manager()
    db_manager.init_control_plane(
        settings.postgres_uri,
        ControlPlanePoolConfig.from_settings(settings),
    )
    await db_manager.validate_postgres_version()

    get_data_plane_engine_registry().init_data_plane(DataPlanePoolConfig.from_settings(settings))

    repository = SqlAlchemySessionRepository(db_manager)
    set_session_repository(repository)
    logger.info("  Session Store: PostgreSQL (SQLAlchemy ORM)")

    config_service = get_config_service_dep()
    await config_service.bootstrap_from_db()
    settings = get_settings()

    logger.info(f"  LLM Provider: {settings.llm.get_provider()}")
    logger.info(f"  LLM Model: {settings.llm.get_model()}")
    if settings.langfuse.is_configured():
        logger.info("  LangFuse: Enabled")

    if settings.query_backend == "adk":
        logger.info("  Query engine: Google ADK (shared PostgreSQL engine)")
    elif settings.checkpointer.is_postgres():
        logger.info("  Checkpointer: PostgreSQL")
        setup_checkpointer()
    else:
        logger.info("  Checkpointer: In-memory")

    yield

    logger.info("EasySQL API shutting down...")

    from easysql.retrieval.runtime import reset_retrieval_runtime
    from easysql_api.deps import clear_config_service, clear_session_repository
    from easysql_api.infrastructure.db_manager import get_control_plane_db_manager

    clear_session_repository()
    clear_config_service()
    reset_retrieval_runtime()
    get_data_plane_engine_registry().dispose_all()
    from easysql_agentic.runtime import close_adk_sessions

    await close_adk_sessions()
    await get_control_plane_db_manager().dispose()

    await close_checkpointer_pool()


def create_app() -> FastAPI:
    app = FastAPI(
        title="EasySQL API",
        description="Enterprise Text2SQL API with Neo4j and Milvus",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api/v1", tags=["Health"])
    app.include_router(query_router, prefix="/api/v1", tags=["Query"])
    app.include_router(execute_router, prefix="/api/v1", tags=["Execute"])
    app.include_router(chart_router, prefix="/api/v1", tags=["Chart"])
    app.include_router(sessions_router, prefix="/api/v1", tags=["Sessions"])
    app.include_router(pipeline_router, prefix="/api/v1", tags=["Pipeline"])
    app.include_router(config_router, prefix="/api/v1", tags=["Config"])
    app.include_router(few_shot_router, prefix="/api/v1", tags=["Few-Shot"])
    app.include_router(agent_tools_router, prefix="/api/v1", tags=["Agent Tools"])

    from easysql_agentic.api import router as wiki_router

    app.include_router(wiki_router, prefix="/api/v1", tags=["Knowledge Wiki"])

    return app


app = create_app()
