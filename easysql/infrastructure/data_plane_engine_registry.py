"""Data-plane SQLAlchemy engine registry for target databases."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from easysql.configuration.models import DatabaseConfig
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class DataPlanePoolConfig:
    """SQLAlchemy pool settings shared by data-plane engines."""

    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    pool_pre_ping: bool = True

    @classmethod
    def from_settings(cls, settings: object) -> DataPlanePoolConfig:
        defaults = cls()
        return cls(
            pool_size=int(getattr(settings, "data_plane_pool_size", defaults.pool_size)),
            max_overflow=int(getattr(settings, "data_plane_max_overflow", defaults.max_overflow)),
            pool_timeout=int(getattr(settings, "data_plane_pool_timeout", defaults.pool_timeout)),
            pool_recycle=int(getattr(settings, "data_plane_pool_recycle", defaults.pool_recycle)),
            pool_pre_ping=bool(
                getattr(settings, "data_plane_pool_pre_ping", defaults.pool_pre_ping)
            ),
        )

    def to_engine_kwargs(self) -> dict[str, int | bool]:
        return {
            "pool_size": self.pool_size,
            "max_overflow": self.max_overflow,
            "pool_timeout": self.pool_timeout,
            "pool_recycle": self.pool_recycle,
            "pool_pre_ping": self.pool_pre_ping,
        }


class DataPlaneEngineRegistry:
    """Owns sync SQLAlchemy engines for target (data-plane) databases."""

    def __init__(self) -> None:
        self._engines: dict[str, Engine] = {}
        self._pool_config: DataPlanePoolConfig = DataPlanePoolConfig()

    def init_data_plane(self, pool_config: DataPlanePoolConfig | None = None) -> None:
        self._pool_config = pool_config or DataPlanePoolConfig()

    def get_engine(self, config: DatabaseConfig) -> Engine:
        key = config.name.lower()
        engine = self._engines.get(key)
        if engine is not None:
            return engine

        engine = create_engine(
            config.get_connection_string(),
            hide_parameters=True,
            **self._pool_config.to_engine_kwargs(),
        )
        self._engines[key] = engine
        logger.debug("Created data-plane engine for {} ({})", config.name, config.db_type)
        return engine

    def dispose(self, name: str) -> None:
        key = name.lower()
        engine = self._engines.pop(key, None)
        if engine is not None:
            engine.dispose()
            logger.debug("Disposed data-plane engine for {}", name)

    def dispose_all(self) -> None:
        for name, engine in list(self._engines.items()):
            engine.dispose()
            logger.debug("Disposed data-plane engine for {}", name)
        self._engines.clear()


_data_plane_engine_registry = DataPlaneEngineRegistry()


def get_data_plane_engine_registry() -> DataPlaneEngineRegistry:
    return _data_plane_engine_registry
