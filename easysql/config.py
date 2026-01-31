"""
Configuration management for EasySql.

Loads configuration from environment variables with support for .env files.
Uses Pydantic Settings for validation and type coercion.
"""

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from easysql.utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseConfig:
    """Configuration for a single source database."""

    def __init__(
        self,
        name: str,
        db_type: str,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        schema: str | None = None,
        system_type: str = "UNKNOWN",
        description: str = "",
    ):
        self.name = name
        self.db_type = db_type.lower()
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.schema = schema
        self.system_type = system_type
        self.description = description

    def get_default_schema(self) -> str:
        """Get default schema based on database type."""
        if self.schema:
            return self.schema
        if self.db_type == "mysql":
            return self.database  # MySQL uses database as schema
        elif self.db_type == "postgresql":
            return "public"
        elif self.db_type == "oracle":
            return self.user.upper()  # Oracle uses user as schema
        elif self.db_type == "sqlserver":
            return "dbo"
        else:
            return "public"

    def get_connection_string(self) -> str:
        """Generate SQLAlchemy connection string based on database type."""
        if self.db_type == "mysql":
            return f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        elif self.db_type == "postgresql":
            return f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        elif self.db_type == "oracle":
            # Oracle using oracledb driver (thin mode by default)
            return f"oracle+oracledb://{self.user}:{self.password}@{self.host}:{self.port}/?service_name={self.database}"
        elif self.db_type == "sqlserver":
            # SQL Server using pyodbc driver
            return f"mssql+pyodbc://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}?driver=ODBC+Driver+17+for+SQL+Server"
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")

    def __repr__(self) -> str:
        return f"DatabaseConfig(name={self.name}, type={self.db_type}, database={self.database}, schema={self.get_default_schema()})"


class CheckpointerConfig(BaseSettings):
    """
    Configuration for LangGraph state persistence.

    Supports PostgreSQL for production or in-memory for development.
    All settings can be overridden via CHECKPOINTER_* environment variables.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Storage backend: "memory" or "postgres"
    backend: str = Field(
        default="memory",
        alias="checkpointer_backend",
        description="Checkpointer backend: memory or postgres",
    )

    # PostgreSQL connection settings
    postgres_host: str = Field(
        default="localhost", alias="checkpointer_postgres_host", description="PostgreSQL host"
    )
    postgres_port: int = Field(
        default=5432, alias="checkpointer_postgres_port", description="PostgreSQL port"
    )
    postgres_user: str = Field(
        default="postgres", alias="checkpointer_postgres_user", description="PostgreSQL user"
    )
    postgres_password: str = Field(
        default="", alias="checkpointer_postgres_password", description="PostgreSQL password"
    )
    postgres_database: str = Field(
        default="easysql", alias="checkpointer_postgres_database", description="PostgreSQL database"
    )

    # Connection pool settings
    pool_min_size: int = Field(
        default=1, alias="checkpointer_pool_min_size", description="Minimum pool connections"
    )
    pool_max_size: int = Field(
        default=10, alias="checkpointer_pool_max_size", description="Maximum pool connections"
    )

    @property
    def postgres_uri(self) -> str:
        """Build PostgreSQL connection URI."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_database}"
        )

    def is_postgres(self) -> bool:
        """Check if using PostgreSQL backend."""
        return self.backend.lower() == "postgres"

    @field_validator("backend")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        valid_backends = {"memory", "postgres"}
        if v.lower() not in valid_backends:
            raise ValueError(f"CHECKPOINTER_BACKEND must be one of {valid_backends}")
        return v.lower()


class LangfuseConfig(BaseSettings):
    """
    Configuration for LangFuse observability.

    LangFuse provides tracing and monitoring for LLM applications.
    All settings can be overridden via LANGFUSE_* environment variables.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    enabled: bool = Field(
        default=False, alias="langfuse_enabled", description="Enable LangFuse tracing"
    )
    public_key: str | None = Field(
        default=None, alias="langfuse_public_key", description="LangFuse public key"
    )
    secret_key: str | None = Field(
        default=None, alias="langfuse_secret_key", description="LangFuse secret key"
    )
    host: str = Field(
        default="https://cloud.langfuse.com",
        alias="langfuse_host",
        description="LangFuse host URL (cloud or self-hosted)",
    )

    def is_configured(self) -> bool:
        """Check if LangFuse is properly configured with required credentials."""
        return bool(self.enabled and self.public_key and self.secret_key)


class LLMConfig(BaseSettings):
    """
    Configuration for the LLM layer.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Query Mode: 'plan' (HITL enabled) or 'fast' (direct execution)
    query_mode: str = Field(default="plan", description="Query execution mode")

    # Model Provider: openai, google_genai, anthropic, etc.
    llm_provider: str = Field(default="openai", description="LLM provider")

    # API Keys & Endpoints (Provider-specific)
    # OpenAI
    openai_api_key: str | None = None
    openai_api_base: str | None = Field(
        default="https://api.openai.com/v1", description="OpenAI API Base URL"
    )

    # Google Gemini
    google_api_key: str | None = None

    # Anthropic
    anthropic_api_key: str | None = None

    # Agent Mode
    use_agent_mode: bool = Field(
        default=False,
        description="Enable SQL Agent mode with ReAct loop for iterative SQL generation and validation",
    )
    agent_max_iterations: int = Field(
        default=15,
        description="Maximum iterations for SQL Agent ReAct loop (safety limit)",
    )

    # Provider-specific Models (Priority: Google > Anthropic > OpenAI)
    google_llm_model: str | None = Field(default=None, description="Google Gemini model name")
    anthropic_llm_model: str | None = Field(default=None, description="Anthropic Claude model name")
    openai_llm_model: str = Field(default="gpt-4o", description="OpenAI model name (fallback)")

    # Optional: Model for planning/analyze phase (query analysis, clarification)
    # If not specified, falls back to the resolved primary model
    model_planning: str | None = Field(
        default=None, description="Optional model for analyze/clarify phase"
    )

    # Retry Configuration
    max_sql_retries: int = Field(default=3, description="Max SQL generation retries")

    def get_model(self) -> str:
        """Get the primary model based on priority: Google > Anthropic > OpenAI.

        Also auto-selects the provider based on which model is configured.
        """
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
    def validate_query_mode(cls, v: str) -> str:
        if v.lower() not in ["plan", "fast"]:
            raise ValueError("QUERY_MODE must be 'plan' or 'fast'")
        return v.lower()


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings can be overridden via environment variables.
    Database configurations are dynamically parsed from DB_<NAME>_* variables.
    """

    # Default .env file, can be overridden by Settings(_env_file=...)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",  # Allow extra fields for dynamic DB configs
    )

    # Neo4j Configuration
    neo4j_uri: str = Field(default="bolt://localhost:7687", description="Neo4j connection URI")
    neo4j_user: str = Field(default="neo4j", description="Neo4j username")
    neo4j_password: str = Field(default="", description="Neo4j password")
    neo4j_database: str = Field(
        default="neo4j", description="Neo4j database name (requires Neo4j 4.0+)"
    )

    # Milvus Configuration
    milvus_uri: str = Field(default="http://localhost:19530", description="Milvus connection URI")
    milvus_token: str | None = Field(default=None, description="Milvus authentication token")
    milvus_collection_prefix: str = Field(
        default="", description="Prefix for Milvus collection names"
    )

    # Embedding Configuration
    embedding_provider: str = Field(
        default="local", description="Embedding provider: local, openai_api, tei"
    )
    embedding_model: str = Field(
        default="BAAI/bge-large-zh-v1.5", description="Embedding model name/identifier"
    )
    embedding_dimension: int = Field(default=1024, description="Embedding vector dimension")
    embedding_api_base: str | None = Field(
        default=None, description="API base URL for openai_api/tei providers"
    )
    embedding_api_key: str | None = Field(
        default=None, description="API key for embedding service (if required)"
    )
    embedding_device: str | None = Field(
        default=None, description="Device for local inference: cpu, cuda, or None (auto)"
    )
    embedding_cache_dir: str | None = Field(
        default=None, description="Cache directory for local models"
    )
    embedding_timeout: float = Field(default=60.0, description="Request timeout for API providers")

    # Pipeline Configuration
    batch_size: int = Field(default=1000, description="Batch size for database operations")
    enable_schema_extraction: bool = Field(default=True, description="Enable schema extraction")
    enable_neo4j_write: bool = Field(default=True, description="Enable Neo4j write")
    enable_milvus_write: bool = Field(default=True, description="Enable Milvus write")

    # Logging Configuration
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: str | None = Field(default=None, description="Log file path")

    # ===== Retrieval Configuration =====

    # Search settings
    retrieval_search_top_k: int = Field(
        default=5, description="Number of tables from Milvus search"
    )
    retrieval_expand_fk: bool = Field(
        default=True, description="Expand tables via FK relationships"
    )
    retrieval_expand_max_depth: int = Field(default=1, description="FK expansion depth")

    # Semantic filter settings
    semantic_filter_enabled: bool = Field(default=True, description="Enable semantic filtering")
    semantic_filter_threshold: float = Field(
        default=0.4, description="Minimum score for semantic filter"
    )
    semantic_filter_min_tables: int = Field(default=3, description="Minimum tables to keep")

    # Core tables that should never be filtered
    core_tables: str = Field(
        default="patient,employee,department,drug_dictionary,diagnosis_dictionary",
        description="Comma-separated core tables that won't be filtered",
    )

    # Bridge table protection
    bridge_protection_enabled: bool = Field(default=True, description="Protect bridge tables")
    bridge_max_hops: int = Field(default=3, description="Max hops for bridge detection")

    # LLM filter settings (Legacy/Retrieval layer)
    llm_filter_enabled: bool = Field(default=False, description="Enable LLM-based table filtering")
    llm_filter_max_tables: int = Field(default=8, description="Max tables after LLM filtering")
    llm_filter_model: str = Field(default="deepseek-chat", description="LLM model for filtering")
    llm_api_key: str | None = Field(default=None, description="LLM API key")
    llm_api_base: str | None = Field(default=None, description="LLM API base URL")

    # ===== Few-Shot Configuration =====
    few_shot_enabled: bool = Field(
        default=False, description="Enable few-shot learning with similar examples"
    )
    few_shot_max_examples: int = Field(
        default=3, description="Maximum number of few-shot examples to include"
    )
    few_shot_min_similarity: float = Field(
        default=0.6, description="Minimum similarity score for few-shot retrieval"
    )
    few_shot_collection_name: str = Field(
        default="few_shot_examples", description="Milvus collection name for few-shot examples"
    )

    # ===== Session Persistence Configuration =====
    session_backend: str = Field(
        default="memory", description="Session storage backend: memory or postgres"
    )
    session_postgres_uri: str | None = Field(
        default=None, description="PostgreSQL URI for session storage (if backend=postgres)"
    )

    def is_session_postgres(self) -> bool:
        """Check if session storage uses PostgreSQL backend."""
        return self.session_backend.lower() == "postgres"

    def get_session_postgres_uri(self) -> str | None:
        """Resolve the PostgreSQL URI for session storage.

        Falls back to checkpointer URI when session_postgres_uri is not set.
        """
        if self.session_postgres_uri:
            return self.session_postgres_uri
        if self.checkpointer.is_postgres():
            logger.warning(
                "SESSION_POSTGRES_URI not set; falling back to checkpointer Postgres URI"
            )
            return self.checkpointer.postgres_uri
        return None

    # ===== Code Context Configuration =====
    code_context_enabled: bool = Field(
        default=False, description="Enable code context retrieval for Text2SQL"
    )
    code_context_search_top_k: int = Field(
        default=5, description="Number of code chunks to retrieve"
    )
    code_context_score_threshold: float = Field(
        default=0.3, description="Minimum relevance score for code retrieval"
    )
    code_context_max_snippets: int = Field(
        default=3, description="Maximum code snippets to include in context"
    )
    code_context_cache_dir: str = Field(
        default=".code_context_cache", description="Directory for file hash cache"
    )
    code_context_supported_languages: str = Field(
        default="csharp,python,java,javascript,typescript",
        description="Comma-separated list of supported languages",
    )
    code_context_collection_prefix: str = Field(
        default="",
        description="Prefix for code context Milvus collection names",
    )

    @property
    def code_context_languages_list(self) -> list[str]:
        """Parse supported languages into list."""
        if not self.code_context_supported_languages:
            return []
        return [
            lang.strip()
            for lang in self.code_context_supported_languages.split(",")
            if lang.strip()
        ]

    # --- LLM Layer Configs (New) ---
    llm: LLMConfig = Field(default_factory=LLMConfig)

    # --- Checkpointer (State Persistence) ---
    checkpointer: CheckpointerConfig = Field(default_factory=CheckpointerConfig)

    # --- Observability ---
    langfuse: LangfuseConfig = Field(default_factory=LangfuseConfig)

    @property
    def core_tables_list(self) -> list[str]:
        """Parse core_tables string into list."""
        if not self.core_tables:
            return []
        return [t.strip() for t in self.core_tables.split(",") if t.strip()]

    # Dynamically parsed database configurations
    _databases: dict[str, DatabaseConfig] = {}

    @model_validator(mode="before")
    @classmethod
    def parse_database_configs(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Parse DB_<NAME>_* environment variables into database configurations."""
        # Also load from environment if not in data
        env_data = {k.lower(): v for k, v in os.environ.items()}
        merged = {**env_data, **{k.lower(): v for k, v in data.items()}}

        # Find all database prefixes (DB_<NAME>_TYPE pattern)
        db_pattern = re.compile(r"^db_([a-zA-Z0-9_]+)_type$", re.IGNORECASE)
        db_names = set()

        for key in merged.keys():
            match = db_pattern.match(key)
            if match:
                db_names.add(match.group(1).upper())

        # Parse each database configuration
        databases = {}
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
                )
                databases[db_name.lower()] = config
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse database config {db_name}: {e}")

        # Store in a special key for later retrieval
        data["_parsed_databases"] = databases
        return data

    @property
    def databases(self) -> dict[str, DatabaseConfig]:
        """Get all configured database connections."""
        return getattr(self, "_parsed_databases", {})

    @field_validator("embedding_provider")
    @classmethod
    def validate_embedding_provider(cls, v: str) -> str:
        valid_providers = {"local", "openai_api", "tei"}
        if v.lower() not in valid_providers:
            raise ValueError(f"EMBEDDING_PROVIDER must be one of {valid_providers}")
        return v.lower()

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper_v = v.upper()
        if upper_v not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return upper_v

    @field_validator("session_backend")
    @classmethod
    def validate_session_backend(cls, v: str) -> str:
        valid_backends = {"memory", "postgres"}
        if v.lower() not in valid_backends:
            raise ValueError(f"SESSION_BACKEND must be one of {valid_backends}")
        return v.lower()


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.

    Returns:
        Settings: Application settings instance
    """
    return Settings()


def load_settings(env_file: str | Path | None = None) -> Settings:
    """
    Load settings from a specific .env file.

    Args:
        env_file: Path to .env file (optional)

    Returns:
        Settings: Application settings instance
    """
    # Clear cache to ensure fresh settings
    get_settings.cache_clear()

    if env_file:
        # Use pydantic-settings native _env_file parameter
        # Note: we ignore type error here because _env_file is handled by BaseSettings __init__
        return Settings(_env_file=env_file)  # type: ignore
    return get_settings()
