from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Annotated, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from easysql.config import Settings
from easysql_api.deps import SessionStoreType, get_session_store_dep, get_settings_dep

router = APIRouter()

_start_time = datetime.now(timezone.utc)


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


class InfoResponse(BaseModel):
    name: str
    version: str
    query_mode: str
    llm_provider: str
    llm_model: str
    databases_configured: int
    uptime_seconds: float


class MetricsResponse(BaseModel):
    active_sessions: int
    uptime_seconds: float
    timestamp: datetime


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/info", response_model=InfoResponse)
async def get_info(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> InfoResponse:
    uptime = (datetime.now(timezone.utc) - _start_time).total_seconds()

    return InfoResponse(
        name="EasySQL",
        version="0.1.0",
        query_mode=settings.llm.query_mode,
        llm_provider=settings.llm.get_provider(),
        llm_model=settings.llm.get_model(),
        databases_configured=len(settings.databases),
        uptime_seconds=uptime,
    )


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    store: Annotated[SessionStoreType, Depends(get_session_store_dep)],
) -> MetricsResponse:
    uptime = (datetime.now(timezone.utc) - _start_time).total_seconds()

    count_result = store.count()
    if inspect.iscoroutine(count_result):
        active_sessions = await count_result
    else:
        active_sessions = cast(int, count_result)

    return MetricsResponse(
        active_sessions=active_sessions,
        uptime_seconds=uptime,
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/ready")
async def readiness_check() -> dict:
    return {"status": "ready"}


@router.get("/live")
async def liveness_check() -> dict:
    return {"status": "live"}
