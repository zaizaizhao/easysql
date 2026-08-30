from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

from easysql.config import CheckpointerConfig, LangfuseConfig, LLMConfig, Settings, load_settings


def test_nested_config_models_are_not_independent_settings_loaders() -> None:
    assert not issubclass(LLMConfig, BaseSettings)
    assert not issubclass(CheckpointerConfig, BaseSettings)
    assert not issubclass(LangfuseConfig, BaseSettings)


def test_load_settings_env_file_populates_nested_config(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_URI=postgresql://user:pass@localhost:5432/easysql",
                "QUERY_MODE=fast",
                "LLM_TEMPERATURE=1.0",
                "CHECKPOINTER_BACKEND=postgres",
                "LANGFUSE_ENABLED=true",
                "LANGFUSE_BASE_URL=https://langfuse.example.com",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(env_file)

    assert settings.llm.query_mode == "fast"
    assert settings.llm.temperature == 1.0
    assert settings.checkpointer.backend == "postgres"
    assert settings.langfuse.enabled is True
    assert settings.langfuse.host == "https://langfuse.example.com"


def test_postgres_uri_derives_sqlalchemy_async_and_psycopg_uris() -> None:
    settings = Settings(
        _env_file=None,
        postgres_uri="postgresql://user:pass@db.local:5432/easysql",
    )

    assert (
        settings.postgres_sqlalchemy_async_uri
        == "postgresql+asyncpg://user:pass@db.local:5432/easysql"
    )
    assert settings.postgres_psycopg_uri == "postgresql://user:pass@db.local:5432/easysql"


def test_postgres_pool_settings_are_loaded_from_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "POSTGRES_POOL_SIZE=12",
                "POSTGRES_MAX_OVERFLOW=24",
                "POSTGRES_POOL_TIMEOUT=45",
                "POSTGRES_POOL_RECYCLE=1800",
                "POSTGRES_POOL_PRE_PING=false",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(env_file)

    assert settings.postgres_pool_size == 12
    assert settings.postgres_max_overflow == 24
    assert settings.postgres_pool_timeout == 45
    assert settings.postgres_pool_recycle == 1800
    assert settings.postgres_pool_pre_ping is False


def test_postgres_uri_driver_normalization_strips_sqlalchemy_driver_for_psycopg() -> None:
    settings = Settings(
        _env_file=None,
        postgres_uri="postgresql+asyncpg://user:pass@db.local:5432/easysql",
    )

    assert (
        settings.postgres_sqlalchemy_async_uri
        == "postgresql+asyncpg://user:pass@db.local:5432/easysql"
    )
    assert settings.postgres_psycopg_uri == "postgresql://user:pass@db.local:5432/easysql"


def test_project_namespace_does_not_replace_neo4j_database() -> None:
    settings = Settings(
        _env_file=None,
        project_namespace="medical",
        neo4j_database="neo4j",
    )

    assert settings.project_namespace == "medical"
    assert settings.neo4j_database == "neo4j"
    assert settings.milvus_collection_prefix == "medical"
