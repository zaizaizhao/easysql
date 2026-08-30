from __future__ import annotations

import ast
import asyncio
import uuid
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from easysql_api.infrastructure.persistence.config_repository import (
    ConfigRepository,
    ConfigUpsertItem,
)
from easysql_api.infrastructure.persistence.models import SessionModel
from easysql_api.infrastructure.persistence.session_repository import (
    SqlAlchemySessionRepository,
)


def test_config_repository_uses_control_plane_transaction_provider() -> None:
    session = _FakeConfigSession()
    provider = _FakeSessionProvider(session)
    repository = ConfigRepository(provider)

    asyncio.run(
        repository.upsert_many(
            [
                ConfigUpsertItem(
                    category="llm",
                    key="query_mode",
                    value="fast",
                    value_type="str",
                    is_secret=False,
                )
            ]
        )
    )

    assert provider.entered == 1
    assert session.executed_count == 1


def test_session_repository_uses_control_plane_transaction_provider_for_create() -> None:
    session = _FakeSessionRepositorySession()
    provider = _FakeSessionProvider(session)
    repository = SqlAlchemySessionRepository(provider)
    session_id = str(uuid.uuid4())

    created = asyncio.run(repository.create(session_id, db_name="his"))

    assert provider.entered == 1
    assert session.added_models
    assert session.added_models[0].id == uuid.UUID(session_id)
    assert created.session_id == session_id
    assert created.db_name == "his"


def test_repositories_do_not_manage_transactions_directly() -> None:
    paths = [
        Path("easysql_api/infrastructure/persistence/config_repository.py"),
        Path("easysql_api/infrastructure/persistence/session_repository.py"),
    ]

    direct_calls = {str(path): _find_direct_transaction_calls(path) for path in paths}

    assert direct_calls == {str(path): [] for path in paths}


def _find_direct_transaction_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in {"commit", "rollback"}:
            calls.append(f"{node.func.attr}:{node.lineno}")
    return calls


class _FakeSessionProvider:
    def __init__(self, session: Any) -> None:
        self._session = session
        self.entered = 0

    def session(self) -> AbstractAsyncContextManager[AsyncSession]:
        return _FakeSessionContext(self)


class _FakeSessionContext:
    def __init__(self, provider: _FakeSessionProvider) -> None:
        self._provider = provider

    async def __aenter__(self) -> Any:
        self._provider.entered += 1
        return self._provider._session

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class _FakeConfigSession:
    def __init__(self) -> None:
        self.executed_count = 0

    async def execute(self, statement: Any) -> None:
        self.executed_count += 1

    async def commit(self) -> None:
        raise AssertionError("Repository must not commit directly")

    async def rollback(self) -> None:
        raise AssertionError("Repository must not roll back directly")


class _FakeSessionRepositorySession:
    def __init__(self) -> None:
        self.added_models: list[SessionModel] = []

    def add(self, model: SessionModel) -> None:
        self.added_models.append(model)

    async def flush(self) -> None:
        return None

    async def refresh(self, model: SessionModel) -> None:
        now = datetime.now(timezone.utc)
        model.created_at = now
        model.updated_at = now

    async def commit(self) -> None:
        raise AssertionError("Repository must not commit directly")

    async def rollback(self) -> None:
        raise AssertionError("Repository must not roll back directly")
