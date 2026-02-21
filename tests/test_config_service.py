from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest

from easysql.config import get_runtime_overrides, get_settings, replace_runtime_overrides
from easysql_api.infrastructure.persistence.config_repository import ConfigUpsertItem
from easysql_api.services.config_service import ConfigService


@dataclass
class FakeConfigRow:
    category: str
    key: str
    value: str
    value_type: str
    is_secret: bool
    updated_at: datetime


class FakeConfigRepository:
    def __init__(self, rows: list[FakeConfigRow] | None = None):
        self.rows = rows or []

    async def load_all(self) -> list[FakeConfigRow]:
        return list(self.rows)

    async def upsert_many(self, items: list[ConfigUpsertItem]) -> None:
        now = datetime.now(timezone.utc)
        for item in items:
            existing = next(
                (row for row in self.rows if row.category == item.category and row.key == item.key),
                None,
            )
            if existing is None:
                self.rows.append(
                    FakeConfigRow(
                        category=item.category,
                        key=item.key,
                        value=item.value,
                        value_type=item.value_type,
                        is_secret=item.is_secret,
                        updated_at=now,
                    )
                )
            else:
                existing.value = item.value
                existing.value_type = item.value_type
                existing.is_secret = item.is_secret
                existing.updated_at = now

    async def delete_category(self, category: str) -> int:
        before = len(self.rows)
        self.rows = [row for row in self.rows if row.category != category]
        return before - len(self.rows)


class FakeInvalidator:
    def __init__(self) -> None:
        self.invalidated: list[set[str]] = []
        self.warmed: list[set[str]] = []

    def invalidate(self, tags: set[str]) -> None:
        self.invalidated.append(set(tags))
        get_settings.cache_clear()

    def warmup(self, tags: set[str]) -> None:
        self.warmed.append(set(tags))


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _reset_runtime_overrides() -> None:
    replace_runtime_overrides({})
    get_settings.cache_clear()


def test_bootstrap_from_db_loads_runtime_overrides() -> None:
    _reset_runtime_overrides()
    repo = FakeConfigRepository(
        [
            FakeConfigRow(
                category="llm",
                key="query_mode",
                value="fast",
                value_type="str",
                is_secret=False,
                updated_at=datetime.now(timezone.utc),
            )
        ]
    )
    service = ConfigService(repository=repo)

    _run(service.bootstrap_from_db())

    assert get_settings().llm.query_mode == "fast"
    assert get_runtime_overrides().get("llm.query_mode") == "fast"

    _reset_runtime_overrides()


def test_update_category_persists_and_invalidates() -> None:
    _reset_runtime_overrides()
    repo = FakeConfigRepository()
    invalidator = FakeInvalidator()
    service = ConfigService(repository=repo, invalidator=invalidator)

    result = _run(
        service.update_category(
            "llm",
            {
                "max_sql_retries": 5,
                "use_agent_mode": True,
            },
            warmup=True,
        )
    )

    assert sorted(result["updated"]) == ["max_sql_retries", "use_agent_mode"]
    assert get_runtime_overrides()["llm.max_sql_retries"] == 5
    assert get_runtime_overrides()["llm.use_agent_mode"] is True
    assert invalidator.invalidated
    assert {"graph", "settings"}.issubset(invalidator.invalidated[-1])
    assert invalidator.warmed

    _reset_runtime_overrides()


def test_update_llm_temperature() -> None:
    _reset_runtime_overrides()
    repo = FakeConfigRepository()
    invalidator = FakeInvalidator()
    service = ConfigService(repository=repo, invalidator=invalidator)

    result = _run(
        service.update_category(
            "llm",
            {
                "temperature": 1.0,
            },
            warmup=True,
        )
    )

    assert result["updated"] == ["temperature"]
    assert get_runtime_overrides()["llm.temperature"] == 1.0
    assert invalidator.invalidated
    assert invalidator.warmed

    _reset_runtime_overrides()


def test_update_llm_temperature_out_of_range_raises() -> None:
    _reset_runtime_overrides()
    repo = FakeConfigRepository()
    service = ConfigService(repository=repo, invalidator=FakeInvalidator())

    with pytest.raises(ValueError, match=r"value must be in \[0, 2\]"):
        _run(
            service.update_category(
                "llm",
                {
                    "temperature": 2.1,
                },
            )
        )

    _reset_runtime_overrides()


def test_update_category_ignores_masked_secret() -> None:
    _reset_runtime_overrides()
    repo = FakeConfigRepository()
    service = ConfigService(repository=repo, invalidator=FakeInvalidator())

    result = _run(
        service.update_category(
            "llm",
            {
                "openai_api_key": "sk-***xyz",
            },
        )
    )

    assert result["updated"] == []
    assert result["invalidate_tags"] == []
    _reset_runtime_overrides()


def test_get_editable_config_includes_metadata() -> None:
    _reset_runtime_overrides()
    repo = FakeConfigRepository()
    service = ConfigService(repository=repo, invalidator=FakeInvalidator())

    result = _run(service.get_editable_config())
    query_mode = result["llm"]["query_mode"]
    langfuse_host = result["langfuse"]["host"]

    assert query_mode["settings_path"] == "llm.query_mode"
    assert query_mode["env_var"] == "QUERY_MODE"
    assert "enum_plan_fast" in query_mode["constraints"]
    assert "settings" in query_mode["invalidate_tags"]
    assert langfuse_host["env_var"] == "LANGFUSE_BASE_URL"

    _reset_runtime_overrides()


def test_delete_category_removes_overrides() -> None:
    _reset_runtime_overrides()
    repo = FakeConfigRepository(
        [
            FakeConfigRow(
                category="few_shot",
                key="few_shot_enabled",
                value="true",
                value_type="bool",
                is_secret=False,
                updated_at=datetime.now(timezone.utc),
            )
        ]
    )
    invalidator = FakeInvalidator()
    service = ConfigService(repository=repo, invalidator=invalidator)

    _run(service.bootstrap_from_db())
    before = _run(service.get_editable_config())
    assert before["few_shot"]["few_shot_enabled"]["is_overridden"] is True

    result = _run(service.delete_category("few_shot", warmup=True))
    assert result["deleted"] == 1
    assert "few_shot_enabled" not in [row.key for row in repo.rows]
    after = _run(service.get_editable_config())
    assert after["few_shot"]["few_shot_enabled"]["is_overridden"] is False

    _reset_runtime_overrides()
