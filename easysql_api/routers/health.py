from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from easysql.config import Settings
from easysql_api.deps import get_session_repository_dep, get_settings_dep
from easysql_api.domain.repositories.session_repository import SessionRepository

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
    repository: Annotated[SessionRepository, Depends(get_session_repository_dep)],
) -> MetricsResponse:
    uptime = (datetime.now(timezone.utc) - _start_time).total_seconds()

    active_sessions = await repository.count()

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
