"""Repository interface for session persistence."""

from __future__ import annotations

from typing import Protocol

from easysql_api.domain.entities.message import Message
from easysql_api.domain.entities.session import Session
from easysql_api.domain.entities.turn import Turn
from easysql_api.domain.value_objects.query_status import QueryStatus


class SessionRepository(Protocol):
    async def create(self, session_id: str, db_name: str | None = None) -> Session: ...

    async def get(self, session_id: str) -> Session | None: ...

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[Session]: ...

    async def count(self) -> int: ...

    async def delete(self, session_id: str) -> bool: ...

    async def update_status(self, session_id: str, status: QueryStatus) -> None: ...

    async def update_session_fields(self, session_id: str, **kwargs: object) -> None: ...

    async def save_turns(self, session_id: str, turns: list[Turn]) -> None: ...

    async def add_message(
        self,
        session_id: str,
        *,
        message_id: str | None,
        thread_id: str | None,
        role: str,
        content: str | None,
        parent_id: str | None = None,
        generated_sql: str | None = None,
        tables_used: list[str] | None = None,
        validation_passed: bool | None = None,
        user_answer: str | None = None,
        clarification_questions: list[str] | None = None,
    ) -> str: ...

    async def get_message(self, message_id: str) -> Message | None: ...

    async def mark_as_few_shot(self, message_id: str, is_few_shot: bool = True) -> None: ...
