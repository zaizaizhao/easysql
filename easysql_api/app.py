from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from easysql_api.routers import (
    query_router,
    sessions_router,
    pipeline_router,
    config_router,
    health_router,
)
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("EasySQL API starting up...")
    yield
    logger.info("EasySQL API shutting down...")


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
    app.include_router(sessions_router, prefix="/api/v1", tags=["Sessions"])
    app.include_router(pipeline_router, prefix="/api/v1", tags=["Pipeline"])
    app.include_router(config_router, prefix="/api/v1", tags=["Config"])

    return app


app = create_app()
