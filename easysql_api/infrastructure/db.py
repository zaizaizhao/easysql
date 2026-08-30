"""Compatibility facade for control-plane SQLAlchemy async sessions."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from easysql_api.infrastructure.db_manager import (
    ControlPlanePoolConfig,
    get_control_plane_db_manager,
)


def init_engine(uri: str, pool_config: ControlPlanePoolConfig | None = None) -> None:
    get_control_plane_db_manager().init_control_plane(uri, pool_config)


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return get_control_plane_db_manager().get_sessionmaker()


async def dispose_engine() -> None:
    await get_control_plane_db_manager().dispose()
