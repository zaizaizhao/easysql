"""Control-plane PostgreSQL connection management."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from easysql.configuration.postgres import (
    normalize_postgres_uri_for_sqlalchemy_async,
    postgres_database_name,
    postgres_uri_with_database,
)
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


class ControlPlaneSessionProvider(Protocol):
    """Provides managed control-plane SQLAlchemy sessions."""

    def session(self) -> AbstractAsyncContextManager[AsyncSession]:
        """Return an async context manager that owns transaction boundaries."""
        ...


@dataclass(frozen=True)
class ControlPlanePoolConfig:
    """SQLAlchemy pool settings for the PostgreSQL control plane."""

    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 3600
    pool_pre_ping: bool = True

    @classmethod
    def from_settings(cls, settings: object) -> ControlPlanePoolConfig:
        defaults = cls()
        return cls(
            pool_size=int(getattr(settings, "postgres_pool_size", defaults.pool_size)),
            max_overflow=int(getattr(settings, "postgres_max_overflow", defaults.max_overflow)),
            pool_timeout=int(getattr(settings, "postgres_pool_timeout", defaults.pool_timeout)),
            pool_recycle=int(getattr(settings, "postgres_pool_recycle", defaults.pool_recycle)),
            pool_pre_ping=bool(getattr(settings, "postgres_pool_pre_ping", defaults.pool_pre_ping)),
        )

    def to_engine_kwargs(self) -> dict[str, int | bool]:
        return {
            "pool_size": self.pool_size,
            "max_overflow": self.max_overflow,
            "pool_timeout": self.pool_timeout,
            "pool_recycle": self.pool_recycle,
            "pool_pre_ping": self.pool_pre_ping,
        }


class ControlPlaneDatabaseManager:
    """Owns the async SQLAlchemy engine used by API persistence."""

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    def init_control_plane(
        self,
        uri: str,
        pool_config: ControlPlanePoolConfig | None = None,
    ) -> None:
        if self._engine is not None:
            return

        config = pool_config or ControlPlanePoolConfig()
        normalized_uri = normalize_postgres_uri_for_sqlalchemy_async(uri)
        self._engine = create_async_engine(normalized_uri, **config.to_engine_kwargs())
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)

    def get_engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError(
                "Control-plane database engine not initialized. " "Call init_control_plane() first."
            )
        return self._engine

    def get_sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        if self._sessionmaker is None:
            raise RuntimeError(
                "Control-plane database sessionmaker not initialized. "
                "Call init_control_plane() first."
            )
        return self._sessionmaker

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        sessionmaker = self.get_sessionmaker()
        async with sessionmaker() as db:
            try:
                yield db
            except BaseException:
                await db.rollback()
                raise
            else:
                await db.commit()

    async def validate_postgres_version(self, min_major: int = 13) -> None:
        engine = self.get_engine()
        async with engine.connect() as conn:
            result = await conn.execute(text("SHOW server_version"))
            version = str(result.scalar_one())

        major_version = parse_postgres_major_version(version)
        if major_version < min_major:
            raise RuntimeError(
                f"PostgreSQL {min_major}+ required for EasySQL control plane; " f"found {version}."
            )

    async def dispose(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
        self._engine = None
        self._sessionmaker = None


async def ensure_control_plane_database_exists(uri: str) -> None:
    """Create the control-plane database on the same server if absent."""
    import psycopg
    from psycopg import sql

    admin_uri = postgres_uri_with_database(uri, "postgres")
    db_name = postgres_database_name(uri)

    async with await psycopg.AsyncConnection.connect(admin_uri, autocommit=True) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
            )
            row = await cursor.fetchone()
            if row is None:
                await cursor.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name))
                )
                logger.info("Created control-plane database '{}'", db_name)


def parse_postgres_major_version(version: str) -> int:
    match = re.search(r"\b(\d+)(?:\.\d+)?\b", version)
    if match is None:
        raise ValueError(f"Unable to parse PostgreSQL major version from {version!r}")
    return int(match.group(1))


_control_plane_db_manager = ControlPlaneDatabaseManager()


def get_control_plane_db_manager() -> ControlPlaneDatabaseManager:
    return _control_plane_db_manager


def get_db_manager() -> ControlPlaneDatabaseManager:
    return get_control_plane_db_manager()
