"""Credential-backed PostgreSQL dblink connection lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg2.extensions import make_dsn
from sqlalchemy import text

from easysql.configuration.models import DatabaseConfig
from easysql.federation.scope import DatabaseTarget
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class DblinkEndpoint:
    """Address of a target database as seen by the PostgreSQL server."""

    host: str
    port: int


class DblinkConnectionError(RuntimeError):
    """A credential-backed dblink connection failed without exposing secrets."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def classify_dblink_error(exc: Exception) -> str:
    """Map driver errors to stable, credential-free status reasons."""
    message = str(exc).lower()
    if "password authentication failed" in message:
        return "password_authentication_failed"
    if "password is required" in message or "does not request a password" in message:
        return "password_authentication_required"
    if "could not translate host name" in message:
        return "host_not_found"
    if "connection refused" in message:
        return "connection_refused"
    if any(
        marker in message
        for marker in ("timeout expired", "timed out", "connection timeout", "connect timeout")
    ):
        return "connection_timeout"
    if "permission denied" in message or "must be superuser" in message:
        return "permission_denied"
    if "dblink" in message and ("does not exist" in message or "undefinedfunction" in message):
        return "extension_missing"
    return "remote_connection_failed"


class DblinkSessionManager:
    """Open named dblink sessions from saved database credentials and clean them up."""

    def __init__(self, *, connect_timeout_seconds: int = 5) -> None:
        self._connect_timeout_seconds = max(1, int(connect_timeout_seconds))

    def connect(
        self,
        connection: Any,
        *,
        source: DatabaseTarget,
        target: DatabaseTarget,
        connection_name: str,
        statement_timeout_seconds: int,
    ) -> str:
        """Open a fresh named connection without foreign servers or user mappings."""
        try:
            open_names = self.get_open_connections(connection)
            if connection_name in open_names:
                self.disconnect(connection, connection_name)

            endpoint = self._resolve_endpoint(connection, source.config, target.config)
            conninfo = self._build_conninfo(
                target.config,
                endpoint,
                statement_timeout_seconds=statement_timeout_seconds,
            )
            connection.execute(
                text("SELECT dblink_connect(:connection_name, :conninfo)"),
                {
                    "connection_name": connection_name,
                    "conninfo": conninfo,
                },
            )
            return connection_name
        except DblinkConnectionError:
            raise
        except Exception as exc:  # noqa: BLE001 - converted to a secret-free domain error
            reason = classify_dblink_error(exc)
            raise DblinkConnectionError(
                reason,
                f"Cannot open dblink connection from '{source.name}' to '{target.name}' "
                f"({reason})",
            ) from exc

    @staticmethod
    def get_open_connections(connection: Any) -> set[str]:
        try:
            names = connection.execute(text("SELECT dblink_get_connections()")).scalar_one()
            return set(names or [])
        except Exception as exc:  # noqa: BLE001 - converted to a secret-free domain error
            reason = classify_dblink_error(exc)
            if reason == "remote_connection_failed":
                reason = "extension_missing"
            raise DblinkConnectionError(
                reason,
                f"dblink connection management is unavailable ({reason})",
            ) from exc

    @staticmethod
    def disconnect(connection: Any, connection_name: str) -> None:
        connection.execute(
            text("SELECT dblink_disconnect(:connection_name)"),
            {"connection_name": connection_name},
        )

    def disconnect_many(self, connection: Any, connection_names: set[str]) -> None:
        for connection_name in sorted(connection_names, reverse=True):
            try:
                self.disconnect(connection, connection_name)
            except Exception as exc:  # noqa: BLE001 - cleanup is best effort
                logger.warning(
                    "Failed to clean up dblink connection {}: {}",
                    connection_name,
                    type(exc).__name__,
                )

    def _build_conninfo(
        self,
        config: DatabaseConfig,
        endpoint: DblinkEndpoint,
        *,
        statement_timeout_seconds: int,
    ) -> str:
        timeout_ms = max(1, int(statement_timeout_seconds)) * 1000
        return make_dsn(
            host=endpoint.host,
            port=endpoint.port,
            dbname=config.database,
            user=config.user,
            password=config.password,
            connect_timeout=self._connect_timeout_seconds,
            application_name=f"easysql_dblink_{config.name.lower()}",
            options=(
                "-csearch_path= "
                "-cdefault_transaction_read_only=on "
                f"-cstatement_timeout={timeout_ms}"
            ),
        )

    @staticmethod
    def _resolve_endpoint(
        connection: Any,
        source: DatabaseConfig,
        target: DatabaseConfig,
    ) -> DblinkEndpoint:
        """Translate same-cluster host port mappings to the server's actual endpoint.

        The development API reaches PostgreSQL through ``localhost:55432``, while
        dblink originates inside PostgreSQL and must use the container address and
        internal port. When two configurations use the same endpoint and the
        target database exists in the current cluster, the server can report the
        correct internal address itself.
        """
        same_endpoint = source.host.strip().lower() == target.host.strip().lower() and int(
            source.port
        ) == int(target.port)
        if same_endpoint:
            try:
                target_is_local = bool(
                    connection.execute(
                        text("SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = :database)"),
                        {"database": target.database},
                    ).scalar_one()
                )
                if not target_is_local:
                    return DblinkEndpoint(host=target.host, port=int(target.port))
                row = connection.execute(
                    text(
                        "SELECT host(inet_server_addr()) AS server_host, "
                        "inet_server_port() AS server_port"
                    )
                ).one()
                server_host, server_port = row[0], row[1]
                if server_host and server_port:
                    return DblinkEndpoint(host=str(server_host), port=int(server_port))
            except Exception as exc:  # noqa: BLE001 - use the configured endpoint as fallback
                logger.debug(
                    "Could not resolve PostgreSQL server-side endpoint for {}: {}",
                    source.name,
                    type(exc).__name__,
                )

        return DblinkEndpoint(host=target.host, port=int(target.port))
