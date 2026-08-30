from __future__ import annotations

import asyncio

import pytest

from easysql_api.infrastructure.db_manager import (
    ControlPlaneDatabaseManager,
    ControlPlanePoolConfig,
    parse_postgres_major_version,
)


def test_init_control_plane_normalizes_uri_and_applies_pool_config(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_create_async_engine(uri: str, **kwargs):
        calls.append({"uri": uri, **kwargs})
        return object()

    def fake_async_sessionmaker(engine, **kwargs):
        return {"engine": engine, **kwargs}

    monkeypatch.setattr(
        "easysql_api.infrastructure.db_manager.create_async_engine",
        fake_create_async_engine,
    )
    monkeypatch.setattr(
        "easysql_api.infrastructure.db_manager.async_sessionmaker",
        fake_async_sessionmaker,
    )

    manager = ControlPlaneDatabaseManager()
    manager.init_control_plane(
        "postgresql://user:pass@localhost:5432/easysql",
        ControlPlanePoolConfig(
            pool_size=7,
            max_overflow=11,
            pool_timeout=13,
            pool_recycle=17,
            pool_pre_ping=False,
        ),
    )

    assert calls == [
        {
            "uri": "postgresql+asyncpg://user:pass@localhost:5432/easysql",
            "pool_size": 7,
            "max_overflow": 11,
            "pool_timeout": 13,
            "pool_recycle": 17,
            "pool_pre_ping": False,
        }
    ]


def test_session_context_commits_on_success() -> None:
    asyncio.run(_assert_session_context_commits_on_success())


async def _assert_session_context_commits_on_success() -> None:
    fake_session = _FakeAsyncSession()
    manager = ControlPlaneDatabaseManager()
    manager._sessionmaker = _FakeSessionMaker(fake_session)

    async with manager.session() as session:
        assert session is fake_session

    assert fake_session.committed is True
    assert fake_session.rolled_back is False


def test_session_context_rolls_back_on_error() -> None:
    asyncio.run(_assert_session_context_rolls_back_on_error())


async def _assert_session_context_rolls_back_on_error() -> None:
    fake_session = _FakeAsyncSession()
    manager = ControlPlaneDatabaseManager()
    manager._sessionmaker = _FakeSessionMaker(fake_session)

    with pytest.raises(RuntimeError, match="boom"):
        async with manager.session():
            raise RuntimeError("boom")

    assert fake_session.committed is False
    assert fake_session.rolled_back is True


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("16.2 (Homebrew)", 16),
        ("13.11", 13),
        ("PostgreSQL 15.5 on x86_64-apple-darwin", 15),
    ],
)
def test_parse_postgres_major_version(version: str, expected: int) -> None:
    assert parse_postgres_major_version(version) == expected


class _FakeAsyncSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class _FakeSessionContext:
    def __init__(self, session: _FakeAsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeAsyncSession:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeSessionMaker:
    def __init__(self, session: _FakeAsyncSession) -> None:
        self._session = session

    def __call__(self) -> _FakeSessionContext:
        return _FakeSessionContext(self._session)
