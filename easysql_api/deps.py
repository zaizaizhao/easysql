from __future__ import annotations

from easysql.config import Settings, get_settings
from easysql_api.domain.repositories.session_repository import SessionRepository
from easysql_api.services.chart_service import ChartService, get_chart_service
from easysql_api.services.execute_service import ExecuteService, get_execute_service
from easysql_api.services.query_service import QueryService, get_query_service

_session_repository: SessionRepository | None = None


def get_settings_dep() -> Settings:
    return get_settings()


def get_session_repository_dep() -> SessionRepository:
    if _session_repository is None:
        raise RuntimeError(
            "SessionRepository not initialized. Ensure app lifespan initialized it."
        )
    return _session_repository


def set_session_repository(repository: SessionRepository) -> None:
    global _session_repository
    _session_repository = repository


def clear_session_repository() -> None:
    global _session_repository
    _session_repository = None


def get_query_service_dep() -> QueryService:
    repository = get_session_repository_dep()
    return get_query_service(repository=repository)


def get_execute_service_dep() -> ExecuteService:
    return get_execute_service()


def get_chart_service_dep() -> ChartService:
    return get_chart_service()
