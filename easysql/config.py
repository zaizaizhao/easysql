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
        self.system_type = system_type
        self.description = description

    def get_connection_string(self) -> str:
        """Generate connection string based on database type."""
        if self.db_type == "mysql":
            return f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        elif self.db_type == "postgresql":
            return f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")

    def __repr__(self) -> str:
        return f"DatabaseConfig(name={self.name}, type={self.db_type}, database={self.database})"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings can be overridden via environment variables.
    Database configurations are dynamically parsed from DB_<NAME>_* variables.
    """

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

    # Milvus Configuration
    milvus_uri: str = Field(default="http://localhost:19530", description="Milvus connection URI")
    milvus_token: str | None = Field(default=None, description="Milvus authentication token")

    # Embedding Configuration
    embedding_model: str = Field(
        default="BAAI/bge-large-zh-v1.5", description="Sentence transformer model name"
    )
    embedding_dimension: int = Field(default=1024, description="Embedding vector dimension")

    # Pipeline Configuration
    batch_size: int = Field(default=1000, description="Batch size for database operations")
    enable_schema_extraction: bool = Field(default=True, description="Enable schema extraction")
    enable_neo4j_write: bool = Field(default=True, description="Enable Neo4j write")
    enable_milvus_write: bool = Field(default=True, description="Enable Milvus write")

    # Logging Configuration
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: str | None = Field(default=None, description="Log file path")

    # Dynamically parsed database configurations
    _databases: list[DatabaseConfig] = []

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
        databases = []
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
                    system_type=merged.get(f"{prefix}system_type", "UNKNOWN"),
                    description=merged.get(f"{prefix}description", ""),
                )
                databases.append(config)
            except (ValueError, TypeError) as e:
                print(f"Warning: Failed to parse database config {db_name}: {e}")

        # Store in a special key for later retrieval
        data["_parsed_databases"] = databases
        return data

    @property
    def databases(self) -> list[DatabaseConfig]:
        """Get all configured database connections."""
        return getattr(self, "_parsed_databases", [])

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper_v = v.upper()
        if upper_v not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return upper_v


@lru_cache()
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
    if env_file:
        os.environ["ENV_FILE"] = str(env_file)
    # Clear cache to reload
    get_settings.cache_clear()
    return get_settings()
