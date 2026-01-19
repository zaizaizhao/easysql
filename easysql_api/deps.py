from __future__ import annotations

from typing import TYPE_CHECKING

from easysql.config import Settings, get_settings
from easysql_api.services.execute_service import ExecuteService, get_execute_service
from easysql_api.services.query_service import QueryService, get_query_service
from easysql_api.services.session_store import SessionStore, get_session_store

if TYPE_CHECKING:
    pass


def get_settings_dep() -> Settings:
    return get_settings()


def get_session_store_dep() -> SessionStore:
    return get_session_store()


def get_query_service_dep() -> QueryService:
    return get_query_service()


def get_execute_service_dep() -> ExecuteService:
    return get_execute_service()
