"""Typed configuration models for EasySQL."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from easysql.configuration.postgres import (
    is_postgres_uri,
    normalize_postgres_uri_for_psycopg,
    normalize_postgres_uri_for_sqlalchemy_async,
    postgres_database_name,
    postgres_uri_with_database,
)
from easysql.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_POSTGRES_URI = "postgresql://postgres:postgres@localhost:5432/easysql"


@dataclass
class DatabaseConfig:
    """Configuration for a single source database."""

    name: str
    db_type: str
    host: str
    port: int
    user: str
    password: str
    database: str
    schema: str | None = None
    system_type: str = "UNKNOWN"
    description: str = ""
    dblink_server: str | None = None
    dblink_connection_name: str | None = None

    def __post_init__(self) -> None:
        self.db_type = self.db_type.lower()

    def get_default_schema(self) -> str:
        """Get default schema based on database type."""
        if self.schema:
            return self.schema
        if self.db_type == "mysql":
            return self.database
        if self.db_type == "postgresql":
            return "public"
        if self.db_type == "oracle":
            return self.user.upper()
        if self.db_type == "sqlserver":
            return "dbo"
        return "public"

    def get_connection_string(self) -> str:
        """Generate SQLAlchemy connection string based on database type."""
        if self.db_type == "mysql":
            return (
                f"mysql+pymysql://{self.user}:{self.password}"
                f"@{self.host}:{self.port}/{self.database}"
            )
        if self.db_type == "postgresql":
            return (
                f"postgresql+psycopg2://{self.user}:{self.password}"
                f"@{self.host}:{self.port}/{self.database}"
            )
        if self.db_type == "oracle":
            return (
                f"oracle+oracledb://{self.user}:{self.password}"
                f"@{self.host}:{self.port}/?service_name={self.database}"
            )
        if self.db_type == "sqlserver":
            return (
                f"mssql+pyodbc://{self.user}:{self.password}"
                f"@{self.host}:{self.port}/{self.database}"
                "?driver=ODBC+Driver+17+for+SQL+Server"
            )
        raise ValueError(f"Unsupported database type: {self.db_type}")

    def get_dblink_server(self) -> str:
        """Return a legacy foreign-server name retained for config compatibility."""
        return self.dblink_server or f"{self.name.lower()}_server"

    def get_dblink_connection_name(self) -> str:
        """Return the session-local dblink connection name for this database."""
        return self.dblink_connection_name or f"{self.name.lower()}_conn"

    def __repr__(self) -> str:
        return (
            f"DatabaseConfig(name={self.name}, type={self.db_type}, "
            f"database={self.database}, schema={self.get_default_schema()})"
        )


class CheckpointerConfig(BaseModel):
    """Configuration for LangGraph state persistence."""

    model_config = ConfigDict(extra="ignore")

    backend: str = Field(default="memory", description="Checkpointer backend: memory or postgres")
    pool_min_size: int = Field(default=2, description="Minimum pool connections")
    pool_max_size: int = Field(default=20, description="Maximum pool connections")

    def is_postgres(self) -> bool:
        """Check if using PostgreSQL backend."""
        return self.backend.lower() == "postgres"

    @field_validator("backend")
    @classmethod
    def validate_backend(cls, value: str) -> str:
        valid_backends = {"memory", "postgres"}
        normalized = value.lower()
        if normalized not in valid_backends:
            raise ValueError(f"CHECKPOINTER_BACKEND must be one of {valid_backends}")
        return normalized


class LangfuseConfig(BaseModel):
    """Configuration for LangFuse observability."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = Field(default=False, description="Enable LangFuse tracing")
    public_key: str | None = Field(default=None, description="LangFuse public key")
    secret_key: str | None = Field(default=None, description="LangFuse secret key")
    host: str = Field(
        default="https://cloud.langfuse.com",
        description="LangFuse base URL (cloud or self-hosted)",
    )

    def is_configured(self) -> bool:
        """Check if LangFuse is properly configured with required credentials."""
        return bool(self.enabled and self.public_key and self.secret_key)


class LLMConfig(BaseModel):
    """Configuration for the LLM layer."""

    model_config = ConfigDict(extra="ignore")

    query_mode: str = Field(default="plan", description="Query execution mode")
    llm_provider: str = Field(default="openai", description="LLM provider")
    openai_api_key: str | None = None
    openai_api_base: str | None = Field(
        default="https://api.openai.com/v1", description="OpenAI API Base URL"
    )
    google_api_key: str | None = None
    anthropic_api_key: str | None = None
    use_agent_mode: bool = Field(default=False, description="Enable SQL Agent mode")
    agent_max_iterations: int = Field(default=15, description="Maximum SQL Agent iterations")
    agent_timeout_seconds: int = Field(
        default=240,
        ge=1,
        description="Maximum wall-clock seconds for one SQL Agent execution",
    )
    query_timeout_seconds: int = Field(
        default=300,
        ge=1,
        description="Maximum wall-clock seconds for one end-to-end query",
    )
    google_llm_model: str | None = Field(default=None, description="Google Gemini model name")
    anthropic_llm_model: str | None = Field(default=None, description="Anthropic Claude model")
    openai_llm_model: str = Field(default="gpt-4o", description="OpenAI model name")
    model_planning: str | None = Field(default=None, description="Optional planning model")
    temperature: float = Field(default=0.0, description="Sampling temperature")
    max_sql_retries: int = Field(default=3, description="Max SQL generation retries")

    def get_model(self) -> str:
        """Get the primary model based on priority: Google > Anthropic > OpenAI."""
        if self.google_llm_model and self.google_api_key:
            return self.google_llm_model
        if self.anthropic_llm_model and self.anthropic_api_key:
            return self.anthropic_llm_model
        return self.openai_llm_model

    def get_provider(self) -> str:
        """Get the provider based on model priority: Google > Anthropic > OpenAI."""
        if self.google_llm_model and self.google_api_key:
            return "google_genai"
        if self.anthropic_llm_model and self.anthropic_api_key:
            return "anthropic"
        return "openai"

    @field_validator("query_mode")
    @classmethod
    def validate_query_mode(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"plan", "fast"}:
            raise ValueError("QUERY_MODE must be 'plan' or 'fast'")
        return normalized

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, value: float) -> float:
        if value < 0 or value > 2:
            raise ValueError("TEMPERATURE must be in [0, 2]")
        return value


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    postgres_uri: str = Field(
        default=DEFAULT_POSTGRES_URI,
        description="PostgreSQL URI for EasySQL control-plane storage",
    )
    postgres_pool_size: int = Field(default=10, description="Control-plane pool size")
    postgres_max_overflow: int = Field(
        default=20,
        description="Control-plane pool overflow connections",
    )
    postgres_pool_timeout: int = Field(
        default=30,
        description="Control-plane pool checkout timeout in seconds",
    )
    postgres_pool_recycle: int = Field(
        default=3600,
        description="Control-plane pool connection recycle seconds",
    )
    postgres_pool_pre_ping: bool = Field(
        default=True,
        description="Enable SQLAlchemy pool pre-ping for control-plane connections",
    )

    data_plane_pool_size: int = Field(default=5, description="Data-plane pool size per database")
    data_plane_max_overflow: int = Field(
        default=10,
        description="Data-plane pool overflow connections per database",
    )
    data_plane_pool_timeout: int = Field(
        default=30,
        description="Data-plane pool checkout timeout in seconds",
    )
    data_plane_pool_recycle: int = Field(
        default=3600,
        description="Data-plane pool connection recycle seconds",
    )
    data_plane_pool_pre_ping: bool = Field(
        default=True,
        description="Enable SQLAlchemy pool pre-ping for data-plane connections",
    )

    project_namespace: str = Field(
        default="default",
        description="Application namespace for Milvus prefixes and Neo4j logical scope",
    )

    neo4j_uri: str = Field(default="bolt://localhost:7687", description="Neo4j connection URI")
    neo4j_user: str = Field(default="neo4j", description="Neo4j username")
    neo4j_password: str = Field(default="", description="Neo4j password")
    neo4j_database: str = Field(default="neo4j", description="Neo4j database name")

    milvus_uri: str = Field(default="http://localhost:19530", description="Milvus connection URI")
    milvus_token: str | None = Field(default=None, description="Milvus authentication token")

    embedding_provider: str = Field(
        default="local", description="Embedding provider: local, openai_api, tei"
    )
    embedding_model: str = Field(
        default="BAAI/bge-large-zh-v1.5", description="Embedding model name/identifier"
    )
    embedding_dimension: int = Field(default=1024, description="Embedding vector dimension")
    embedding_api_base: str | None = Field(default=None, description="Embedding API base URL")
    embedding_api_key: str | None = Field(default=None, description="Embedding API key")
    embedding_device: str | None = Field(default=None, description="Local embedding device")
    embedding_cache_dir: str | None = Field(default=None, description="Local model cache dir")

    log_level: str = Field(default="INFO", description="Logging level")
    log_file: str | None = Field(default=None, description="Log file path")

    retrieval_search_top_k: int = Field(default=5, description="Tables from Milvus search")
    retrieval_expand_fk: bool = Field(default=True, description="Expand tables via FK")
    retrieval_expand_max_depth: int = Field(default=1, description="FK expansion depth")
    semantic_filter_enabled: bool = Field(default=True, description="Enable semantic filtering")
    semantic_filter_threshold: float = Field(default=0.4, description="Semantic filter threshold")
    semantic_filter_min_tables: int = Field(default=3, description="Minimum tables to keep")
    core_tables: str = Field(default="", description="Comma-separated core tables")
    bridge_protection_enabled: bool = Field(default=True, description="Protect bridge tables")
    llm_filter_enabled: bool = Field(default=False, description="Enable LLM table filtering")
    llm_filter_max_tables: int = Field(default=8, description="Max tables after LLM filtering")
    llm_filter_model: str = Field(default="deepseek-chat", description="LLM filter model")

    few_shot_enabled: bool = Field(default=False, description="Enable few-shot learning")
    few_shot_max_examples: int = Field(default=3, description="Maximum few-shot examples")
    few_shot_min_similarity: float = Field(default=0.6, description="Few-shot min similarity")

    session_backend: str = Field(default="postgres", description="Session storage backend")

    code_context_enabled: bool = Field(default=False, description="Enable code context retrieval")
    code_context_search_top_k: int = Field(default=5, description="Code chunks to retrieve")
    code_context_score_threshold: float = Field(default=0.3, description="Code score threshold")
    code_context_max_snippets: int = Field(default=3, description="Max code snippets")

    # Flat env bridge fields. These are accepted at the top level so Settings,
    # not nested models, remains the only component that reads .env values.
    query_mode: str | None = Field(default=None, exclude=True, repr=False)
    llm_provider: str | None = Field(default=None, exclude=True, repr=False)
    openai_api_key: str | None = Field(default=None, exclude=True, repr=False)
    openai_api_base: str | None = Field(default=None, exclude=True, repr=False)
    google_api_key: str | None = Field(default=None, exclude=True, repr=False)
    anthropic_api_key: str | None = Field(default=None, exclude=True, repr=False)
    use_agent_mode: bool | None = Field(default=None, exclude=True, repr=False)
    agent_max_iterations: int | None = Field(default=None, exclude=True, repr=False)
    agent_timeout_seconds: int | None = Field(default=None, exclude=True, repr=False)
    query_timeout_seconds: int | None = Field(default=None, exclude=True, repr=False)
    google_llm_model: str | None = Field(default=None, exclude=True, repr=False)
    anthropic_llm_model: str | None = Field(default=None, exclude=True, repr=False)
    openai_llm_model: str | None = Field(default=None, exclude=True, repr=False)
    model_planning: str | None = Field(default=None, exclude=True, repr=False)
    llm_temperature: float | None = Field(default=None, exclude=True, repr=False)
    temperature: float | None = Field(default=None, exclude=True, repr=False)
    max_sql_retries: int | None = Field(default=None, exclude=True, repr=False)
    checkpointer_backend: str | None = Field(default=None, exclude=True, repr=False)
    langfuse_enabled: bool | None = Field(default=None, exclude=True, repr=False)
    langfuse_public_key: str | None = Field(default=None, exclude=True, repr=False)
    langfuse_secret_key: str | None = Field(default=None, exclude=True, repr=False)
    langfuse_base_url: str | None = Field(default=None, exclude=True, repr=False)
    langfuse_host: str | None = Field(default=None, exclude=True, repr=False)

    llm: LLMConfig = Field(default_factory=LLMConfig)
    checkpointer: CheckpointerConfig = Field(default_factory=CheckpointerConfig)
    langfuse: LangfuseConfig = Field(default_factory=LangfuseConfig)
    databases: dict[str, DatabaseConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def bridge_flat_env_to_nested_models(cls, value: Any) -> Any:
        """Map flat env/config keys into the nested application models."""
        if not isinstance(value, dict):
            return value

        data = dict(value)
        _move_flat_keys(
            data,
            "llm",
            [
                ("query_mode", "query_mode"),
                ("llm_provider", "llm_provider"),
                ("openai_api_key", "openai_api_key"),
                ("openai_api_base", "openai_api_base"),
                ("google_api_key", "google_api_key"),
                ("anthropic_api_key", "anthropic_api_key"),
                ("use_agent_mode", "use_agent_mode"),
                ("agent_max_iterations", "agent_max_iterations"),
                ("agent_timeout_seconds", "agent_timeout_seconds"),
                ("query_timeout_seconds", "query_timeout_seconds"),
                ("google_llm_model", "google_llm_model"),
                ("anthropic_llm_model", "anthropic_llm_model"),
                ("openai_llm_model", "openai_llm_model"),
                ("model_planning", "model_planning"),
                ("llm_temperature", "temperature"),
                ("temperature", "temperature"),
                ("max_sql_retries", "max_sql_retries"),
            ],
        )
        _move_flat_keys(
            data,
            "checkpointer",
            [
                ("checkpointer_backend", "backend"),
            ],
        )
        _move_flat_keys(
            data,
            "langfuse",
            [
                ("langfuse_enabled", "enabled"),
                ("langfuse_public_key", "public_key"),
                ("langfuse_secret_key", "secret_key"),
                ("langfuse_base_url", "host"),
                ("langfuse_host", "host"),
            ],
        )

        data["databases"] = _parse_database_configs(data)
        return data

    @property
    def postgres_sqlalchemy_async_uri(self) -> str:
        """PostgreSQL DSN for async SQLAlchemy ORM consumers."""
        return normalize_postgres_uri_for_sqlalchemy_async(self.postgres_uri)

    @property
    def postgres_psycopg_uri(self) -> str:
        """PostgreSQL DSN for psycopg/LangGraph consumers."""
        return normalize_postgres_uri_for_psycopg(self.postgres_uri)

    @property
    def postgres_admin_psycopg_uri(self) -> str:
        """Psycopg DSN for the default admin database on the same server."""
        return postgres_uri_with_database(self.postgres_uri, "postgres")

    @property
    def postgres_database(self) -> str:
        """Control-plane database name from POSTGRES_URI."""
        return postgres_database_name(self.postgres_uri)

    @property
    def milvus_collection_prefix(self) -> str:
        """Milvus collection prefix derived from the project namespace."""
        return self.project_namespace

    @property
    def core_tables_list(self) -> list[str]:
        """Parse core_tables string into a list."""
        if not self.core_tables:
            return []
        return [table.strip() for table in self.core_tables.split(",") if table.strip()]

    def is_session_postgres(self) -> bool:
        """Check if session storage uses PostgreSQL backend."""
        return self.session_backend.lower() == "postgres"

    @field_validator("postgres_uri")
    @classmethod
    def validate_postgres_uri(cls, value: str) -> str:
        if not is_postgres_uri(value):
            raise ValueError("POSTGRES_URI must be a PostgreSQL DSN")
        postgres_database_name(value)
        return value

    @field_validator("project_namespace")
    @classmethod
    def validate_project_namespace(cls, value: str) -> str:
        normalized = value.strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$", normalized):
            raise ValueError(
                "PROJECT_NAMESPACE must start with a letter or underscore and contain only "
                "letters, numbers, and underscores"
            )
        return normalized

    @field_validator("embedding_provider")
    @classmethod
    def validate_embedding_provider(cls, value: str) -> str:
        valid_providers = {"local", "openai_api", "tei"}
        normalized = value.lower()
        if normalized not in valid_providers:
            raise ValueError(f"EMBEDDING_PROVIDER must be one of {valid_providers}")
        return normalized

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = value.upper()
        if normalized not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return normalized

    @field_validator("session_backend")
    @classmethod
    def validate_session_backend(cls, value: str) -> str:
        valid_backends = {"postgres"}
        normalized = value.lower()
        if normalized not in valid_backends:
            raise ValueError(f"SESSION_BACKEND must be one of {valid_backends}")
        return normalized


def _move_flat_keys(
    data: dict[str, Any],
    nested_field: str,
    mappings: list[tuple[str, str]],
) -> None:
    nested = _model_to_dict(_get_case_insensitive(data, nested_field))
    keys = {str(key).lower(): key for key in data}

    for flat_key, nested_key in mappings:
        source_key = keys.get(flat_key.lower())
        if source_key is None or nested_key in nested:
            continue
        nested[nested_key] = data[source_key]

    if nested:
        data[nested_field] = nested


def _get_case_insensitive(data: dict[str, Any], key: str) -> Any:
    lowered = key.lower()
    for candidate, value in data.items():
        if str(candidate).lower() == lowered:
            return value
    return None


def _model_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    if isinstance(value, dict):
        return dict(value)
    return {}


def _parse_database_configs(data: dict[str, Any]) -> dict[str, DatabaseConfig]:
    existing = _get_case_insensitive(data, "databases")
    if isinstance(existing, dict):
        return {
            name.lower(): config if isinstance(config, DatabaseConfig) else DatabaseConfig(**config)
            for name, config in existing.items()
        }

    env_data = {key.lower(): value for key, value in os.environ.items()}
    merged = {**env_data}
    for key, value in data.items():
        merged[str(key).lower()] = value

    db_pattern = re.compile(r"^db_([a-zA-Z0-9_]+)_type$", re.IGNORECASE)
    db_names = set()
    for key in merged:
        match = db_pattern.match(key)
        if match:
            db_names.add(match.group(1).upper())

    databases: dict[str, DatabaseConfig] = {}
    for db_name in db_names:
        prefix = f"db_{db_name.lower()}_"
        try:
            config = DatabaseConfig(
                name=db_name,
                db_type=merged.get(f"{prefix}type", ""),
                host=merged.get(f"{prefix}host", "localhost"),
                port=int(merged.get(f"{prefix}port", 3306)),
                user=merged.get(f"{prefix}user", "root"),
                password=merged.get(f"{prefix}password", ""),
                database=merged.get(f"{prefix}database", ""),
                schema=merged.get(f"{prefix}schema"),
                system_type=merged.get(f"{prefix}system_type", "UNKNOWN"),
                description=merged.get(f"{prefix}description", ""),
                dblink_server=merged.get(f"{prefix}dblink_server"),
                dblink_connection_name=merged.get(f"{prefix}dblink_connection_name"),
            )
            databases[db_name.lower()] = config
        except (ValueError, TypeError) as exc:
            logger.warning("Failed to parse database config {}: {}", db_name, exc)

    return databases
