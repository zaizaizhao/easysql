"""Application service for runtime configuration overrides."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from easysql.config import (
    get_runtime_overrides,
    get_settings,
    remove_runtime_overrides,
    replace_runtime_overrides,
    update_runtime_overrides,
)
from easysql.utils.logger import get_logger
from easysql_api.infrastructure.persistence.config_repository import (
    ConfigRepository,
    ConfigUpsertItem,
)
from easysql_api.services.cache_invalidator import CacheInvalidator
from easysql_api.services.config_schema import (
    CATEGORIES,
    ConfigSpec,
    deserialize_value,
    get_category_specs,
    get_spec,
    serialize_value,
)

logger = get_logger(__name__)


class ConfigService:
    """Coordinates validation, persistence, and runtime cache refresh."""

    def __init__(
        self,
        repository: ConfigRepository,
        invalidator: CacheInvalidator | None = None,
    ):
        self._repository = repository
        self._invalidator = invalidator or CacheInvalidator()

    async def bootstrap_from_db(self) -> None:
        rows = await self._repository.load_all()
        overrides: dict[str, Any] = {}

        for row in rows:
            try:
                spec = get_spec(row.category, row.key)
                value = deserialize_value(row.value, row.value_type)
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning(
                    "Skip invalid persisted config row: category={} key={} reason={}",
                    row.category,
                    row.key,
                    f"{type(exc).__name__}: {exc}",
                )
                continue

            overrides[spec.settings_path] = value

        replace_runtime_overrides(overrides)
        get_settings.cache_clear()

    async def get_overrides(self) -> dict[str, dict[str, dict[str, Any]]]:
        rows = await self._repository.load_all()
        response: dict[str, dict[str, dict[str, Any]]] = {
            category: {} for category in sorted(CATEGORIES)
        }

        for row in rows:
            try:
                spec = get_spec(row.category, row.key)
                value = deserialize_value(row.value, row.value_type)
            except (KeyError, ValueError, TypeError):
                continue

            response[spec.category][spec.key] = {
                "value": self._mask_secret(value) if spec.secret else value,
                "is_secret": spec.secret,
                "updated_at": row.updated_at.isoformat(),
            }

        return response

    async def get_editable_config(self) -> dict[str, dict[str, dict[str, Any]]]:
        settings = get_settings()
        runtime_overrides = get_runtime_overrides()

        data: dict[str, dict[str, dict[str, Any]]] = {
            category: {} for category in sorted(CATEGORIES)
        }
        for category in sorted(CATEGORIES):
            for spec in get_category_specs(category):
                value = self._get_settings_value(settings, spec.settings_path)
                data[category][spec.key] = {
                    "value": self._mask_secret(value) if spec.secret else value,
                    "is_secret": spec.secret,
                    "is_overridden": spec.settings_path in runtime_overrides,
                    "nullable": spec.nullable,
                    "value_type": spec.value_type,
                    "settings_path": spec.settings_path,
                    "env_var": spec.env_var,
                    "constraints": list(spec.constraints),
                    "invalidate_tags": sorted(spec.invalidate_tags),
                }

        return data

    async def update_category(
        self,
        category: str,
        updates: Mapping[str, Any],
        *,
        warmup: bool = False,
    ) -> dict[str, Any]:
        if category not in CATEGORIES:
            raise ValueError(f"Unsupported category: {category}")

        if not updates:
            raise ValueError("No updates provided")

        upsert_items: list[ConfigUpsertItem] = []
        override_patch: dict[str, Any] = {}
        changed_keys: list[str] = []
        invalidate_tags: set[str] = set()

        for key, raw_value in updates.items():
            try:
                spec = get_spec(category, key)
            except KeyError as exc:
                raise ValueError(f"Unsupported config key: {category}.{key}") from exc

            value = self._coerce_value(spec, raw_value)

            if spec.secret and isinstance(value, str) and "***" in value:
                continue

            if spec.validator:
                spec.validator(value)

            value_type, serialized_value = serialize_value(value)
            upsert_items.append(
                ConfigUpsertItem(
                    category=category,
                    key=key,
                    value=serialized_value,
                    value_type=value_type,
                    is_secret=spec.secret,
                )
            )
            override_patch[spec.settings_path] = value
            changed_keys.append(key)
            invalidate_tags.update(spec.invalidate_tags)

        if not upsert_items:
            return {
                "category": category,
                "updated": [],
                "invalidate_tags": [],
            }

        await self._repository.upsert_many(upsert_items)
        update_runtime_overrides(override_patch)
        self._invalidator.invalidate(invalidate_tags)
        if warmup:
            self._invalidator.warmup(invalidate_tags)

        return {
            "category": category,
            "updated": sorted(changed_keys),
            "invalidate_tags": sorted(invalidate_tags),
        }

    async def delete_category(self, category: str, *, warmup: bool = False) -> dict[str, Any]:
        if category not in CATEGORIES:
            raise ValueError(f"Unsupported category: {category}")

        specs = get_category_specs(category)
        deleted = await self._repository.delete_category(category)

        paths = [spec.settings_path for spec in specs]
        invalidate_tags: set[str] = set()
        for spec in specs:
            invalidate_tags.update(spec.invalidate_tags)

        remove_runtime_overrides(paths)
        self._invalidator.invalidate(invalidate_tags)
        if warmup:
            self._invalidator.warmup(invalidate_tags)

        return {
            "category": category,
            "deleted": deleted,
            "message": "Reverted to .env defaults",
            "invalidate_tags": sorted(invalidate_tags),
        }

    @staticmethod
    def _get_settings_value(settings: Any, settings_path: str) -> Any:
        target = settings
        for segment in settings_path.split("."):
            target = getattr(target, segment)
        return target

    @staticmethod
    def _mask_secret(value: Any) -> str | None:
        if value is None:
            return None

        value_str = str(value)
        if not value_str:
            return "***"

        if len(value_str) <= 6:
            return "***"

        return f"{value_str[:3]}***{value_str[-3:]}"

    @staticmethod
    def _coerce_value(spec: ConfigSpec, raw_value: Any) -> Any:
        if raw_value is None:
            if not spec.nullable:
                raise ValueError(f"{spec.category}.{spec.key} does not allow null")
            return None

        if spec.value_type == "str":
            if not isinstance(raw_value, str):
                raise ValueError(f"{spec.category}.{spec.key} requires string")
            return raw_value

        if spec.value_type == "bool":
            if isinstance(raw_value, bool):
                return raw_value
            if isinstance(raw_value, str):
                lower = raw_value.strip().lower()
                if lower == "true":
                    return True
                if lower == "false":
                    return False
            raise ValueError(f"{spec.category}.{spec.key} requires boolean")

        if spec.value_type == "int":
            if isinstance(raw_value, bool):
                raise ValueError(f"{spec.category}.{spec.key} requires integer")
            if isinstance(raw_value, int):
                return raw_value
            if isinstance(raw_value, str):
                try:
                    return int(raw_value.strip())
                except ValueError as exc:
                    raise ValueError(f"{spec.category}.{spec.key} requires integer") from exc
            raise ValueError(f"{spec.category}.{spec.key} requires integer")

        if spec.value_type == "float":
            if isinstance(raw_value, bool):
                raise ValueError(f"{spec.category}.{spec.key} requires float")
            if isinstance(raw_value, int | float):
                return float(raw_value)
            if isinstance(raw_value, str):
                try:
                    return float(raw_value.strip())
                except ValueError as exc:
                    raise ValueError(f"{spec.category}.{spec.key} requires float") from exc
            raise ValueError(f"{spec.category}.{spec.key} requires float")

        raise ValueError(
            f"Unsupported value type for {spec.category}.{spec.key}: {spec.value_type}"
        )
