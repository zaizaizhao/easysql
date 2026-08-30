"""Runtime override storage and application for editable configuration."""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import TYPE_CHECKING, Any

from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from easysql.configuration.models import Settings

logger = get_logger(__name__)

_RUNTIME_OVERRIDES: dict[str, Any] = {}
_RUNTIME_OVERRIDES_LOCK = RLock()


def replace_runtime_overrides(overrides: dict[str, Any]) -> None:
    """Replace all runtime overrides with the provided mapping."""
    with _RUNTIME_OVERRIDES_LOCK:
        _RUNTIME_OVERRIDES.clear()
        _RUNTIME_OVERRIDES.update(deepcopy(overrides))


def update_runtime_overrides(patch: dict[str, Any]) -> None:
    """Merge runtime override patches by settings path."""
    with _RUNTIME_OVERRIDES_LOCK:
        _RUNTIME_OVERRIDES.update(deepcopy(patch))


def remove_runtime_overrides(paths: list[str]) -> None:
    """Remove runtime overrides by settings path."""
    with _RUNTIME_OVERRIDES_LOCK:
        for path in paths:
            _RUNTIME_OVERRIDES.pop(path, None)


def get_runtime_overrides() -> dict[str, Any]:
    """Get a copy of current runtime overrides."""
    with _RUNTIME_OVERRIDES_LOCK:
        return deepcopy(_RUNTIME_OVERRIDES)


def apply_runtime_overrides(settings: Settings, overrides: dict[str, Any]) -> Settings:
    """Return a new validated settings instance with runtime overrides applied."""
    if not overrides:
        return settings

    data = settings.model_dump(mode="python")
    for path, value in overrides.items():
        if not _settings_path_exists(settings, path):
            logger.warning("Skip unknown override path: {}", path)
            continue
        _apply_override_path(data, path, value)

    return settings.__class__.model_validate(data)


def _settings_path_exists(settings: Settings, path: str) -> bool:
    target: Any = settings
    for segment in path.split("."):
        if not hasattr(target, segment):
            return False
        target = getattr(target, segment)
    return True


def _apply_override_path(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    target = data
    for part in parts[:-1]:
        nested = target.setdefault(part, {})
        if not isinstance(nested, dict):
            nested = {}
            target[part] = nested
        target = nested

    target[parts[-1]] = value
