from __future__ import annotations

from typing import TYPE_CHECKING

from easysql_api.services.query_service import QueryService, get_query_service
from easysql_api.services.session_store import SessionStore, get_session_store
from easysql.config import Settings, get_settings

if TYPE_CHECKING:
    pass


def get_settings_dep() -> Settings:
    return get_settings()


def get_session_store_dep() -> SessionStore:
    return get_session_store()


def get_query_service_dep() -> QueryService:
    return get_query_service()
