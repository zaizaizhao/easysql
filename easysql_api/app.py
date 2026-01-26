from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from easysql.config import get_settings
from easysql.llm import close_checkpointer_pool, setup_checkpointer
from easysql.utils.logger import get_logger
from easysql_api.routers import (
    config_router,
    execute_router,
    few_shot_router,
    health_router,
    pipeline_router,
    query_router,
    sessions_router,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("EasySQL API starting up...")
    logger.info(f"  LLM Provider: {settings.llm.get_provider()}")
    logger.info(f"  LLM Model: {settings.llm.get_model()}")
    if settings.langfuse.is_configured():
        logger.info("  LangFuse: Enabled")

    if settings.checkpointer.is_postgres():
        logger.info("  Checkpointer: PostgreSQL")
        setup_checkpointer()
    else:
        logger.info("  Checkpointer: In-memory")

    yield
    logger.info("EasySQL API shutting down...")
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
    app.include_router(sessions_router, prefix="/api/v1", tags=["Sessions"])
    app.include_router(pipeline_router, prefix="/api/v1", tags=["Pipeline"])
    app.include_router(config_router, prefix="/api/v1", tags=["Config"])
    app.include_router(few_shot_router, prefix="/api/v1", tags=["Few-Shot"])

    return app


app = create_app()
