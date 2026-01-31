"""PostgreSQL-backed session storage implementation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg

from easysql.utils.logger import get_logger
from easysql_api.models.query import QueryStatus
from easysql_api.models.turn import Turn, turn_from_dict, turn_to_dict

logger = get_logger(__name__)


class PgSession:
    """Session data from PostgreSQL."""

    def __init__(
        self,
        session_id: str,
        db_name: str | None = None,
        status: QueryStatus = QueryStatus.PENDING,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        self.session_id = session_id
        self.db_name = db_name
        self.status = status
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)
        self.raw_query: str | None = None
        self.generated_sql: str | None = None
        self.validation_passed: bool | None = None
        self.clarification_questions: list[str] | None = None
        self.state: dict[str, Any] | None = None
        self.turns: list[Turn] = []
        self._turn_counter: int = 0

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def create_turn(self, question: str) -> Turn:
        self._turn_counter += 1
        turn = Turn(
            turn_id=f"turn-{self._turn_counter:03d}",
            question=question,
        )
        self.turns.append(turn)
        self.touch()
        return turn

    def get_current_turn(self) -> Turn | None:
        return self.turns[-1] if self.turns else None

    def get_turn(self, turn_id: str) -> Turn | None:
        for turn in self.turns:
            if turn.turn_id == turn_id:
                return turn
        return None


class PgSessionStore:
    """PostgreSQL-backed session store."""

    def __init__(self, postgres_uri: str):
        self._uri = postgres_uri
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._uri, min_size=2, max_size=10)
            logger.info("PostgreSQL session store connected")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Session store not connected. Call connect() first.")
        return self._pool

    async def create(self, session_id: str, db_name: str | None = None) -> PgSession:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO easysql_sessions (id, db_name, status)
                VALUES ($1, $2, $3)
                """,
                UUID(session_id),
                db_name,
                "pending",
            )
        return PgSession(session_id=session_id, db_name=db_name)

    async def get(self, session_id: str) -> PgSession | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, db_name, status, created_at, updated_at,
                       raw_query, generated_sql, validation_passed, state, turns, title
                FROM easysql_sessions WHERE id = $1
                """,
                UUID(session_id),
            )
            if not row:
                return None

            session = PgSession(
                session_id=str(row["id"]),
                db_name=row["db_name"],
                status=QueryStatus(row["status"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            session.raw_query = row.get("raw_query")
            session.generated_sql = row.get("generated_sql")
            session.validation_passed = row.get("validation_passed")
            session.state = row.get("state")

            turns_data = row.get("turns")
            if turns_data:
                if isinstance(turns_data, str):
                    turns_data = json.loads(turns_data)
                session.turns = [turn_from_dict(t) for t in turns_data]
                session._turn_counter = len(session.turns)

            return session

    async def update_status(self, session_id: str, status: QueryStatus) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE easysql_sessions SET status = $1 WHERE id = $2",
                status.value,
                UUID(session_id),
            )

    async def save_turns(self, session_id: str, turns: list[Turn]) -> None:
        async with self.pool.acquire() as conn:
            turns_json = json.dumps([turn_to_dict(t) for t in turns])
            await conn.execute(
                "UPDATE easysql_sessions SET turns = $1, updated_at = $2 WHERE id = $3",
                turns_json,
                datetime.now(timezone.utc),
                UUID(session_id),
            )

    async def update_session_fields(self, session_id: str, **kwargs: Any) -> None:
        if not kwargs:
            return

        allowed_fields = {
            "raw_query",
            "generated_sql",
            "validation_passed",
            "state",
            "title",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return

        columns = []
        values: list[Any] = []
        for idx, (key, value) in enumerate(updates.items(), start=1):
            columns.append(f"{key} = ${idx}")
            values.append(value)

        values.append(datetime.now(timezone.utc))
        values.append(UUID(session_id))

        set_clause = ", ".join(columns) + f", updated_at = ${len(values)-1}"

        async with self.pool.acquire() as conn:
            await conn.execute(
                f"UPDATE easysql_sessions SET {set_clause} WHERE id = ${len(values)}",
                *values,
            )

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str | None,
        message_id: str | None = None,
        thread_id: str | None = None,
        parent_id: str | None = None,
        generated_sql: str | None = None,
        tables_used: list[str] | None = None,
        validation_passed: bool | None = None,
        user_answer: str | None = None,
        clarification_questions: list[str] | None = None,
    ) -> str:
        columns = []
        values: list[Any] = []

        if message_id:
            columns.append("id")
            values.append(UUID(message_id))

        columns.extend(
            [
                "session_id",
                "parent_id",
                "thread_id",
                "role",
                "content",
                "generated_sql",
                "tables_used",
                "validation_passed",
                "user_answer",
                "clarification_questions",
            ]
        )
        values.extend(
            [
                UUID(session_id),
                UUID(parent_id) if parent_id else None,
                thread_id or session_id,
                role,
                content,
                generated_sql,
                tables_used,
                validation_passed,
                user_answer,
                json.dumps(clarification_questions) if clarification_questions else None,
            ]
        )

        placeholders = ", ".join(f"${idx}" for idx in range(1, len(values) + 1))

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO easysql_messages
                ({columns})
                VALUES ({placeholders})
                RETURNING id
                """.format(columns=", ".join(columns), placeholders=placeholders),
                *values,
            )
            return str(row["id"])

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, session_id, parent_id, thread_id, role, content, generated_sql,
                       tables_used, validation_passed, user_answer, clarification_questions, created_at
                FROM easysql_messages WHERE id = $1
                """,
                UUID(message_id),
            )
            if not row:
                return None
            return dict(row)

    async def mark_as_few_shot(self, message_id: str, is_few_shot: bool = True) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE easysql_messages SET is_few_shot = $1 WHERE id = $2",
                is_few_shot,
                UUID(message_id),
            )

    async def delete(self, session_id: str) -> bool:
        async with self.pool.acquire() as conn:
            result: str = await conn.execute(
                "DELETE FROM easysql_sessions WHERE id = $1",
                UUID(session_id),
            )
            return result == "DELETE 1"

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[PgSession]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, db_name, status, created_at, updated_at,
                       raw_query, generated_sql, validation_passed, state, turns, title
                FROM easysql_sessions
                ORDER BY updated_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
            sessions = []
            for r in rows:
                session = PgSession(
                    session_id=str(r["id"]),
                    db_name=r["db_name"],
                    status=QueryStatus(r["status"]),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                session.raw_query = r.get("raw_query")
                session.generated_sql = r.get("generated_sql")
                session.validation_passed = r.get("validation_passed")
                session.state = r.get("state")
                turns_data = r.get("turns")
                if turns_data:
                    if isinstance(turns_data, str):
                        turns_data = json.loads(turns_data)
                    session.turns = [turn_from_dict(t) for t in turns_data]
                sessions.append(session)
            return sessions

    async def count(self) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM easysql_sessions")
            return row["cnt"] if row else 0
