from __future__ import annotations

from typing import TYPE_CHECKING, Union

from easysql.config import Settings, get_settings
from easysql_api.services.execute_service import ExecuteService, get_execute_service
from easysql_api.services.query_service import QueryService, get_query_service
from easysql_api.services.session_store import SessionStore, get_session_store

if TYPE_CHECKING:
    from easysql_api.services.pg_session_store import PgSessionStore

SessionStoreType = Union[SessionStore, "PgSessionStore"]

_pg_session_store: "PgSessionStore | None" = None


def get_settings_dep() -> Settings:
    return get_settings()


def get_session_store_dep() -> SessionStoreType:
    settings = get_settings()
    if settings.checkpointer.is_postgres():
        if _pg_session_store is None:
            raise RuntimeError(
                "PgSessionStore not initialized. Ensure app lifespan initialized it."
            )
        return _pg_session_store
    return get_session_store()


def set_pg_session_store(store: "PgSessionStore") -> None:
    global _pg_session_store
    _pg_session_store = store


def clear_pg_session_store() -> None:
    global _pg_session_store
    _pg_session_store = None


def get_query_service_dep() -> QueryService:
    return get_query_service()


def get_execute_service_dep() -> ExecuteService:
    return get_execute_service()
