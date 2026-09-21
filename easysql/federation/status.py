"""Real dblink capability checks for a selected database scope."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from easysql.federation.dblink import DblinkConnectionError, DblinkSessionManager
from easysql.federation.scope import DatabaseScope, DatabaseTarget
from easysql.infrastructure import get_data_plane_engine_registry
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from easysql.config import Settings

logger = get_logger(__name__)


@dataclass(frozen=True)
class DblinkRouteStatus:
    source_db: str
    target_db: str
    status: str
    reason: str


@dataclass(frozen=True)
class DatabaseDblinkStatus:
    name: str
    connection_name: str
    status: str
    reason: str
    extension_installed: bool | None
    connect_allowed: bool | None
    routes: list[DblinkRouteStatus] = field(default_factory=list)


@dataclass(frozen=True)
class FederationStatus:
    mode: str
    status: str
    reason: str
    db_names: list[str]
    databases: list[DatabaseDblinkStatus]


class FederationStatusProbe:
    """Check single-DB mode or all dblink routes for a multi-DB scope."""

    def __init__(self, registry: Any | None = None, manager: DblinkSessionManager | None = None):
        self._registry = registry or get_data_plane_engine_registry()
        self._manager = manager or DblinkSessionManager()

    def check(self, settings: Settings, db_names: list[str]) -> FederationStatus:
        normalized = self._normalize_names(settings, db_names)
        if len(normalized) == 1:
            target = settings.databases[normalized[0]]
            return FederationStatus(
                mode="single",
                status="not_required",
                reason="single_database",
                db_names=normalized,
                databases=[
                    DatabaseDblinkStatus(
                        name=normalized[0],
                        connection_name=target.get_dblink_connection_name(),
                        status="not_required",
                        reason="single_database",
                        extension_installed=None,
                        connect_allowed=None,
                    )
                ],
            )

        non_postgres = [
            name for name in normalized if settings.databases[name].db_type != "postgresql"
        ]
        if non_postgres:
            databases = [
                DatabaseDblinkStatus(
                    name=name,
                    connection_name=settings.databases[name].get_dblink_connection_name(),
                    status="unavailable",
                    reason="multi_requires_postgresql",
                    extension_installed=None,
                    connect_allowed=None,
                )
                for name in normalized
            ]
            return FederationStatus(
                mode="dblink",
                status="unavailable",
                reason="multi_requires_postgresql",
                db_names=normalized,
                databases=databases,
            )

        scope = DatabaseScope.resolve(settings, db_names=normalized)
        database_statuses = [self._check_primary(scope, source) for source in scope.targets]
        # A query executes on one primary; reverse routes from remote databases
        # are not required when that primary can reach the entire selected scope.
        ready = any(item.status == "ready" for item in database_statuses)
        return FederationStatus(
            mode="dblink",
            status="ready" if ready else "unavailable",
            reason="ready" if ready else database_statuses[0].reason,
            db_names=normalized,
            databases=database_statuses,
        )

    @staticmethod
    def _normalize_names(settings: Settings, db_names: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw_name in db_names:
            name = str(raw_name).strip().lower()
            if name and name not in normalized:
                normalized.append(name)
        if not normalized:
            raise ValueError("At least one database must be selected")
        missing = [name for name in normalized if name not in settings.databases]
        if missing:
            raise ValueError(f"Database(s) not configured: {', '.join(missing)}")
        return normalized

    def _check_primary(
        self,
        scope: DatabaseScope,
        source: DatabaseTarget,
    ) -> DatabaseDblinkStatus:
        try:
            engine = self._registry.get_engine(source.config)
            with engine.connect() as connection:
                extension_installed = bool(
                    connection.execute(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM pg_extension " "WHERE extname = 'dblink')"
                        )
                    ).scalar_one()
                )
                if not extension_installed:
                    return self._database_failure(source, "extension_missing", False, False)

                connect_allowed = bool(
                    connection.execute(
                        text(
                            "SELECT COALESCE(bool_or(has_function_privilege("
                            "current_user, p.oid, 'EXECUTE')), false) "
                            "FROM pg_proc p WHERE p.proname = 'dblink_connect' "
                            "AND p.pronargs = 2"
                        )
                    ).scalar_one()
                )
                if not connect_allowed:
                    return self._database_failure(
                        source,
                        "connect_permission_missing",
                        True,
                        False,
                    )

                connection.execute(
                    text("SELECT set_config('statement_timeout', :timeout, true)"),
                    {"timeout": "5000ms"},
                )
                routes = [
                    self._check_route(connection, source, target)
                    for target in scope.targets
                    if target.name != source.name
                ]
                failed_route = next((route for route in routes if route.status != "ready"), None)
                return DatabaseDblinkStatus(
                    name=source.name,
                    connection_name=source.dblink_connection_name,
                    status="ready" if failed_route is None else "unavailable",
                    reason="ready" if failed_route is None else failed_route.reason,
                    extension_installed=True,
                    connect_allowed=True,
                    routes=routes,
                )
        except Exception as exc:  # noqa: BLE001 - return a stable status, never credentials
            logger.warning(
                "Dblink primary capability check failed for {}: {}",
                source.name,
                type(exc).__name__,
            )
            return self._database_failure(
                source,
                "primary_connection_failed",
                None,
                None,
            )

    def _check_route(
        self,
        connection: Any,
        source: DatabaseTarget,
        target: DatabaseTarget,
    ) -> DblinkRouteStatus:
        connection_name = f"__easysql_probe_{target.name}_{uuid.uuid4().hex[:8]}"
        connected = False
        try:
            self._manager.connect(
                connection,
                source=source,
                target=target,
                connection_name=connection_name,
                statement_timeout_seconds=5,
            )
            connected = True
            remote_database = connection.execute(
                text(
                    "SELECT remote_database FROM "
                    "dblink(:connection_name, :probe_sql) "
                    "AS probe(remote_database text)"
                ),
                {
                    "connection_name": connection_name,
                    "probe_sql": "SELECT current_database()::text",
                },
            ).scalar_one()
            if str(remote_database) != target.config.database:
                return DblinkRouteStatus(
                    source_db=source.name,
                    target_db=target.name,
                    status="unavailable",
                    reason="remote_database_mismatch",
                )
            return DblinkRouteStatus(
                source_db=source.name,
                target_db=target.name,
                status="ready",
                reason="ready",
            )
        except DblinkConnectionError as exc:
            return DblinkRouteStatus(
                source_db=source.name,
                target_db=target.name,
                status="unavailable",
                reason=exc.reason,
            )
        except Exception as exc:  # noqa: BLE001 - return a stable status, never credentials
            logger.warning(
                "Dblink route check failed from {} to {}: {}",
                source.name,
                target.name,
                type(exc).__name__,
            )
            return DblinkRouteStatus(
                source_db=source.name,
                target_db=target.name,
                status="unavailable",
                reason="remote_query_failed",
            )
        finally:
            if connected:
                try:
                    self._manager.disconnect(connection, connection_name)
                except Exception as exc:  # noqa: BLE001 - best-effort probe cleanup
                    logger.warning(
                        "Failed to clean up dblink probe {}: {}",
                        connection_name,
                        type(exc).__name__,
                    )

    @staticmethod
    def _database_failure(
        source: DatabaseTarget,
        reason: str,
        extension_installed: bool | None,
        connect_allowed: bool | None,
    ) -> DatabaseDblinkStatus:
        return DatabaseDblinkStatus(
            name=source.name,
            connection_name=source.dblink_connection_name,
            status="unavailable",
            reason=reason,
            extension_installed=extension_installed,
            connect_allowed=connect_allowed,
        )
