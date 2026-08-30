"""Application service for runtime configuration overrides."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from sqlalchemy import create_engine, text

from easysql.config import (
    DatabaseConfig,
    get_runtime_overrides,
    get_settings,
    remove_runtime_overrides,
    replace_runtime_overrides,
    update_runtime_overrides,
)
from easysql.federation import FederationStatusProbe
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

DATABASES_CATEGORY = "databases"
DATABASES_KEY = "configured"
DATABASE_INVALIDATE_TAGS = {
    "settings",
    "graph",
    "retrieval_cache",
    "data_plane_engines",
}


class ConfigService:
    """Coordinates validation, persistence, and runtime cache refresh."""

    def __init__(
        self,
        repository: ConfigRepository,
        invalidator: CacheInvalidator | None = None,
        federation_probe: FederationStatusProbe | None = None,
    ):
        self._repository = repository
        self._invalidator = invalidator or CacheInvalidator()
        self._federation_probe = federation_probe or FederationStatusProbe()

    async def bootstrap_from_db(self) -> None:
        rows = await self._repository.load_all()
        overrides: dict[str, Any] = {}

        for row in rows:
            if row.category == DATABASES_CATEGORY and row.key == DATABASES_KEY:
                try:
                    databases = json.loads(row.value)
                    if not isinstance(databases, dict):
                        raise ValueError("database configuration must be an object")
                    overrides["databases"] = databases
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    logger.warning(
                        "Skip invalid persisted database configuration: {}",
                        f"{type(exc).__name__}: {exc}",
                    )
                continue

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

    async def get_database_configs(self) -> list[dict[str, Any]]:
        """Return effective data-plane configurations without passwords."""
        databases = get_settings().databases
        return [
            self._database_public_dict(config)
            for _, config in sorted(databases.items(), key=lambda item: item[0])
        ]

    async def get_database_federation_status(self, db_names: list[str]) -> dict[str, Any]:
        """Probe the actual dblink routes for the selected database scope."""
        status = await asyncio.to_thread(
            self._federation_probe.check,
            get_settings(),
            db_names,
        )
        return asdict(status)

    async def replace_database_configs(
        self,
        raw_databases: list[Mapping[str, Any]],
        *,
        warmup: bool = False,
    ) -> dict[str, Any]:
        """Replace the user-managed database catalog atomically.

        Passwords omitted by the UI are retained for existing logical database
        names. The complete catalog is stored in one secret configuration row so
        readers never observe a partially updated multi-database selection.
        """
        existing = get_settings().databases
        normalized: dict[str, DatabaseConfig] = {}

        for raw in raw_databases:
            payload = dict(raw)
            if "schema_name" in payload:
                payload["schema"] = payload.pop("schema_name")
            name = str(payload.get("name", "")).strip()
            key = name.lower()
            if not key:
                raise ValueError("Database name is required")
            if key in normalized:
                raise ValueError(f"Duplicate database name: {name}")

            previous = existing.get(key)
            password = payload.get("password")
            if password is None or (isinstance(password, str) and "***" in password):
                payload["password"] = previous.password if previous else ""

            payload["name"] = key
            try:
                config = DatabaseConfig(**payload)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid database '{name}': {exc}") from exc
            normalized[key] = config

        serializable = {key: asdict(config) for key, config in normalized.items()}
        await self._repository.upsert_many(
            [
                ConfigUpsertItem(
                    category=DATABASES_CATEGORY,
                    key=DATABASES_KEY,
                    value=json.dumps(serializable, ensure_ascii=False),
                    value_type="json",
                    is_secret=True,
                )
            ]
        )

        update_runtime_overrides({"databases": serializable})
        self._invalidator.invalidate(DATABASE_INVALIDATE_TAGS)
        if warmup:
            self._invalidator.warmup(DATABASE_INVALIDATE_TAGS)

        return {
            "databases": [
                self._database_public_dict(config)
                for _, config in sorted(normalized.items(), key=lambda item: item[0])
            ],
            "total": len(normalized),
            "updated": sorted(normalized),
        }

    async def delete_database_config(
        self,
        name: str,
        *,
        warmup: bool = False,
    ) -> dict[str, Any]:
        key = name.strip().lower()
        current = get_settings().databases
        if key not in current:
            raise ValueError(f"Database '{name}' is not configured")

        remaining = [asdict(config) for db_key, config in current.items() if db_key != key]
        return await self.replace_database_configs(remaining, warmup=warmup)

    async def test_database_config(self, raw_database: Mapping[str, Any]) -> str:
        """Test a submitted configuration without adding it to the engine registry."""
        payload = dict(raw_database)
        if "schema_name" in payload:
            payload["schema"] = payload.pop("schema_name")
        name = str(payload.get("name", "")).strip()
        existing = get_settings().databases.get(name.lower())
        password = payload.get("password")
        if password is None or (isinstance(password, str) and "***" in password):
            payload["password"] = existing.password if existing else ""

        try:
            config = DatabaseConfig(**payload)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid database '{name}': {exc}") from exc

        return await asyncio.to_thread(self._test_connection_sync, config)

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
    def _database_public_dict(config: DatabaseConfig) -> dict[str, Any]:
        return {
            "name": config.name.lower(),
            "type": config.db_type,
            "host": config.host,
            "port": config.port,
            "user": config.user,
            "database": config.database,
            "schema": config.get_default_schema(),
            "system_type": config.system_type,
            "description": config.description,
            "dblink_connection_name": config.get_dblink_connection_name(),
            "has_password": bool(config.password),
        }

    @staticmethod
    def _test_connection_sync(config: DatabaseConfig) -> str:
        engine = create_engine(config.get_connection_string(), pool_pre_ping=True)
        try:
            probe = "SELECT 1 FROM DUAL" if config.db_type == "oracle" else "SELECT 1"
            with engine.connect() as connection:
                connection.execute(text(probe))
            return f"Connected to {config.name} successfully"
        finally:
            engine.dispose()

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
