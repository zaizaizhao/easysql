from __future__ import annotations

import sqlalchemy

from easysql.configuration.models import DatabaseConfig
from easysql.infrastructure.data_plane_engine_registry import (
    DataPlaneEngineRegistry,
    DataPlanePoolConfig,
)


def _make_config(name: str, db_type: str = "mysql") -> DatabaseConfig:
    return DatabaseConfig(
        name=name,
        db_type=db_type,
        host="localhost",
        port=3306,
        user="root",
        password="root",
        database="testdb",
    )


def test_pool_config_from_settings_reads_data_plane_fields() -> None:
    class Settings:
        data_plane_pool_size = 7
        data_plane_max_overflow = 11
        data_plane_pool_timeout = 13
        data_plane_pool_recycle = 17
        data_plane_pool_pre_ping = False

    config = DataPlanePoolConfig.from_settings(Settings())

    assert config == DataPlanePoolConfig(
        pool_size=7,
        max_overflow=11,
        pool_timeout=13,
        pool_recycle=17,
        pool_pre_ping=False,
    )


def test_get_engine_creates_once_and_applies_pool_config(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_create_engine(uri: str, **kwargs):
        calls.append({"uri": uri, **kwargs})
        return object()

    monkeypatch.setattr(
        "easysql.infrastructure.data_plane_engine_registry.create_engine",
        fake_create_engine,
    )

    registry = DataPlaneEngineRegistry()
    registry.init_data_plane(
        DataPlanePoolConfig(
            pool_size=3,
            max_overflow=4,
            pool_timeout=5,
            pool_recycle=6,
            pool_pre_ping=False,
        )
    )

    config = _make_config("HIS")
    first = registry.get_engine(config)
    second = registry.get_engine(config)

    assert first is second
    assert calls == [
        {
            "uri": config.get_connection_string(),
            "hide_parameters": True,
            "pool_size": 3,
            "max_overflow": 4,
            "pool_timeout": 5,
            "pool_recycle": 6,
            "pool_pre_ping": False,
        }
    ]


def test_dispose_all_clears_engines(monkeypatch) -> None:
    disposed: list[str] = []

    class FakeEngine:
        def __init__(self, name: str) -> None:
            self.name = name

        def dispose(self) -> None:
            disposed.append(self.name)

    monkeypatch.setattr(
        "easysql.infrastructure.data_plane_engine_registry.create_engine",
        lambda uri, **kwargs: FakeEngine(uri),
    )

    registry = DataPlaneEngineRegistry()
    registry.get_engine(_make_config("HIS"))
    registry.get_engine(_make_config("CRM", db_type="postgresql"))

    registry.dispose_all()

    assert len(disposed) == 2
    assert registry.get_engine(_make_config("HIS")).name.startswith("mysql+pymysql")


def test_dispose_specific_engine_only_disposes_named(monkeypatch) -> None:
    disposed: list[str] = []

    class FakeEngine:
        def __init__(self, name: str) -> None:
            self.name = name

        def dispose(self) -> None:
            disposed.append(self.name)

    monkeypatch.setattr(
        "easysql.infrastructure.data_plane_engine_registry.create_engine",
        lambda uri, **kwargs: FakeEngine(uri),
    )

    registry = DataPlaneEngineRegistry()
    his_engine = registry.get_engine(_make_config("HIS"))
    crm_engine = registry.get_engine(_make_config("CRM", db_type="postgresql"))

    registry.dispose("his")

    assert disposed == [his_engine.name]
    assert registry.get_engine(_make_config("CRM", db_type="postgresql")) is crm_engine


def test_executor_consumes_registry(monkeypatch) -> None:
    from easysql.config import Settings
    from easysql.llm.tools.executors.sqlalchemy_executor import SqlAlchemyExecutor

    config = _make_config("HIS")
    settings = Settings(databases={"his": config})

    monkeypatch.setattr(
        "easysql.llm.tools.executors.sqlalchemy_executor.get_settings",
        lambda: settings,
    )

    seen: list[DatabaseConfig] = []

    class StubRegistry:
        def get_engine(self, db_config: DatabaseConfig) -> object:
            seen.append(db_config)
            return sqlalchemy.create_engine("sqlite:///:memory:")

    monkeypatch.setattr(
        "easysql.llm.tools.executors.sqlalchemy_executor.get_data_plane_engine_registry",
        lambda: StubRegistry(),
    )

    executor = SqlAlchemyExecutor()
    executor._get_engine("his")

    assert seen == [config]
