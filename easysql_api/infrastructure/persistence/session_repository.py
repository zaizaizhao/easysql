"""SQLAlchemy-backed session repository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from easysql_api.domain.entities.message import Message
from easysql_api.domain.entities.session import Session
from easysql_api.domain.entities.turn import Turn, turn_from_dict, turn_to_dict
from easysql_api.domain.repositories.session_repository import SessionRepository
from easysql_api.domain.value_objects.query_status import QueryStatus
from easysql_api.infrastructure.persistence.models import MessageModel, SessionModel


class SqlAlchemySessionRepository(SessionRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]):
        self._sessionmaker = sessionmaker

    async def create(self, session_id: str, db_name: str | None = None) -> Session:
        async with self._sessionmaker() as db:
            session = SessionModel(
                id=uuid.UUID(session_id),
                db_name=db_name,
                status=QueryStatus.PENDING.value,
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            return _map_session(session)

    async def get(self, session_id: str) -> Session | None:
        async with self._sessionmaker() as db:
            result = await db.execute(
                select(SessionModel).where(SessionModel.id == uuid.UUID(session_id))
            )
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return _map_session(model)

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[Session]:
        async with self._sessionmaker() as db:
            result = await db.execute(
                select(SessionModel)
                .order_by(SessionModel.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            models = result.scalars().all()
            return [_map_session(m) for m in models]

    async def count(self) -> int:
        async with self._sessionmaker() as db:
            result = await db.execute(select(func.count()).select_from(SessionModel))
            return int(result.scalar_one())

    async def delete(self, session_id: str) -> bool:
        async with self._sessionmaker() as db:
            result = await db.execute(
                delete(SessionModel).where(SessionModel.id == uuid.UUID(session_id))
            )
            await db.commit()
            return result.rowcount == 1

    async def update_status(self, session_id: str, status: QueryStatus) -> None:
        async with self._sessionmaker() as db:
            await db.execute(
                update(SessionModel)
                .where(SessionModel.id == uuid.UUID(session_id))
                .values(status=status.value, updated_at=_utc_now())
            )
            await db.commit()

    async def update_session_fields(self, session_id: str, **kwargs: Any) -> None:
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
        updates["updated_at"] = _utc_now()

        async with self._sessionmaker() as db:
            await db.execute(
                update(SessionModel)
                .where(SessionModel.id == uuid.UUID(session_id))
                .values(**updates)
            )
            await db.commit()

    async def save_turns(self, session_id: str, turns: list[Turn]) -> None:
        turns_payload = [turn_to_dict(t) for t in turns]
        async with self._sessionmaker() as db:
            await db.execute(
                update(SessionModel)
                .where(SessionModel.id == uuid.UUID(session_id))
                .values(turns=turns_payload, updated_at=_utc_now())
            )
            await db.commit()

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
    ) -> str:
        message_uuid = uuid.UUID(message_id) if message_id else uuid.uuid4()
        async with self._sessionmaker() as db:
            message = MessageModel(
                id=message_uuid,
                session_id=uuid.UUID(session_id),
                parent_id=uuid.UUID(parent_id) if parent_id else None,
                thread_id=thread_id or session_id,
                role=role,
                content=content,
                generated_sql=generated_sql,
                tables_used=tables_used,
                validation_passed=validation_passed,
                user_answer=user_answer,
                clarification_questions=clarification_questions,
            )
            db.add(message)
            await db.commit()
            return str(message_uuid)

    async def get_message(self, message_id: str) -> Message | None:
        async with self._sessionmaker() as db:
            result = await db.execute(
                select(MessageModel).where(MessageModel.id == uuid.UUID(message_id))
            )
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return _map_message(model)

    async def mark_as_few_shot(self, message_id: str, is_few_shot: bool = True) -> None:
        async with self._sessionmaker() as db:
            await db.execute(
                update(MessageModel)
                .where(MessageModel.id == uuid.UUID(message_id))
                .values(is_few_shot=is_few_shot)
            )
            await db.commit()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _map_session(model: SessionModel) -> Session:
    session = Session(
        session_id=str(model.id),
        db_name=model.db_name,
        status=QueryStatus(model.status),
        created_at=model.created_at,
        updated_at=model.updated_at,
        raw_query=model.raw_query,
        generated_sql=model.generated_sql,
        validation_passed=model.validation_passed,
        state=model.state,
        title=model.title,
    )

    if model.turns:
        session.turns = [turn_from_dict(t) for t in model.turns]
        session._turn_counter = len(session.turns)

    return session


def _map_message(model: MessageModel) -> Message:
    return Message(
        message_id=str(model.id),
        session_id=str(model.session_id),
        thread_id=model.thread_id or str(model.session_id),
        parent_id=str(model.parent_id) if model.parent_id else None,
        role=model.role,
        content=model.content,
        generated_sql=model.generated_sql,
        tables_used=model.tables_used or [],
        validation_passed=model.validation_passed,
        user_answer=model.user_answer,
        clarification_questions=model.clarification_questions,
        created_at=model.created_at,
    )
