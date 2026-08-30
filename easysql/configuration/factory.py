"""Settings factory functions."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values

from easysql.configuration.models import Settings
from easysql.configuration.runtime_overrides import apply_runtime_overrides, get_runtime_overrides


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings with runtime overrides applied."""
    settings = Settings()
    return apply_runtime_overrides(settings, get_runtime_overrides())


def load_settings(env_file: str | Path | None = None) -> Settings:
    """Load settings from a specific .env file or the default cached settings."""
    get_settings.cache_clear()
    if env_file:
        env_values = {
            key.lower(): value
            for key, value in dotenv_values(env_file).items()
            if value is not None
        }
        return Settings(_env_file=None, **env_values)
    return get_settings()
