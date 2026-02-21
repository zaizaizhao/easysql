"""SQLAlchemy-backed session repository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, inspect, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from easysql_api.domain.entities.message import Message
from easysql_api.domain.entities.session import Session, SessionSummary
from easysql_api.domain.entities.turn import Clarification, Turn, TurnStatus
from easysql_api.domain.repositories.session_repository import SessionRepository
from easysql_api.domain.value_objects.query_status import QueryStatus
from easysql_api.infrastructure.persistence.models import (
    ClarificationModel,
    MessageModel,
    SessionModel,
    TurnModel,
)


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
                select(SessionModel)
                .where(SessionModel.id == uuid.UUID(session_id))
                .options(
                    selectinload(SessionModel.turns).selectinload(TurnModel.clarifications),
                    selectinload(SessionModel.messages),
                )
            )
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return _map_session(model)

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[Session]:
        async with self._sessionmaker() as db:
            result = await db.execute(
                select(SessionModel)
                .options(
                    selectinload(SessionModel.turns).selectinload(TurnModel.clarifications),
                    selectinload(SessionModel.messages),
                )
                .order_by(SessionModel.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            models = result.scalars().all()
            return [_map_session(m) for m in models]

    async def list_summaries(self, limit: int = 100, offset: int = 0) -> list[SessionSummary]:
        question_count_subq = (
            select(func.count(TurnModel.id))
            .where(TurnModel.session_id == SessionModel.id)
            .scalar_subquery()
        )
        title_subq = (
            select(TurnModel.question)
            .where(TurnModel.session_id == SessionModel.id)
            .order_by(TurnModel.position.asc(), TurnModel.created_at.asc())
            .limit(1)
            .scalar_subquery()
        )
        question_count = func.coalesce(question_count_subq, 0).label("question_count")
        title = func.coalesce(SessionModel.title, title_subq).label("title")

        async with self._sessionmaker() as db:
            result = await db.execute(
                select(
                    SessionModel.id,
                    SessionModel.db_name,
                    SessionModel.status,
                    SessionModel.created_at,
                    SessionModel.updated_at,
                    question_count,
                    title,
                )
                .order_by(SessionModel.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = result.all()

        summaries: list[SessionSummary] = []
        for row in rows:
            data = row._mapping
            summaries.append(
                SessionSummary(
                    session_id=str(data["id"]),
                    db_name=data["db_name"],
                    status=QueryStatus(data["status"]),
                    created_at=data["created_at"],
                    updated_at=data["updated_at"],
                    question_count=int(data["question_count"] or 0),
                    title=data["title"],
                )
            )
        return summaries

    async def count(self) -> int:
        async with self._sessionmaker() as db:
            result = await db.execute(select(func.count()).select_from(SessionModel))
            return int(result.scalar_one())

    async def delete(self, session_id: str) -> bool:
        async with self._sessionmaker() as db:
            target_id = uuid.UUID(session_id)
            count_result = await db.execute(
                select(func.count()).select_from(SessionModel).where(SessionModel.id == target_id)
            )
            exists = int(count_result.scalar_one()) > 0
            if not exists:
                return False

            await db.execute(delete(SessionModel).where(SessionModel.id == target_id))
            await db.commit()
            return True

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
        async with self._sessionmaker() as db:
            existing_result = await db.execute(
                select(TurnModel)
                .where(TurnModel.session_id == uuid.UUID(session_id))
                .options(selectinload(TurnModel.clarifications))
            )
            existing_turns = {turn.turn_id: turn for turn in existing_result.scalars().all()}
            incoming_ids = {turn.turn_id for turn in turns}

            for turn_id, existing_model in existing_turns.items():
                if turn_id not in incoming_ids:
                    await db.delete(existing_model)

            for position, turn in enumerate(turns):
                model: TurnModel | None = existing_turns.get(turn.turn_id)
                chart_plan = turn.chart_plan
                chart_reasoning = turn.chart_reasoning

                if model:
                    if chart_plan is None and model.chart_plan is not None:
                        chart_plan = model.chart_plan
                    if chart_reasoning is None and model.chart_reasoning is not None:
                        chart_reasoning = model.chart_reasoning

                    model.question = turn.question
                    model.status = turn.status.value
                    model.final_sql = turn.final_sql
                    model.validation_passed = turn.validation_passed
                    model.error = turn.error
                    model.chart_plan = chart_plan
                    model.chart_reasoning = chart_reasoning
                    model.position = position

                    model.clarifications.clear()
                    for idx, clarification in enumerate(turn.clarifications):
                        model.clarifications.append(
                            ClarificationModel(
                                position=idx,
                                questions=clarification.questions,
                                answer=clarification.answer,
                            )
                        )
                else:
                    model = TurnModel(
                        session_id=uuid.UUID(session_id),
                        turn_id=turn.turn_id,
                        question=turn.question,
                        status=turn.status.value,
                        final_sql=turn.final_sql,
                        validation_passed=turn.validation_passed,
                        error=turn.error,
                        chart_plan=chart_plan,
                        chart_reasoning=chart_reasoning,
                        position=position,
                        created_at=turn.created_at,
                    )
                    model.clarifications = [
                        ClarificationModel(
                            position=idx,
                            questions=clarification.questions,
                            answer=clarification.answer,
                        )
                        for idx, clarification in enumerate(turn.clarifications)
                    ]
                    db.add(model)

            await db.execute(
                update(SessionModel)
                .where(SessionModel.id == uuid.UUID(session_id))
                .values(updated_at=_utc_now())
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

    if "turns" not in inspect(model).unloaded:
        session.turns = [_map_turn(t) for t in model.turns]
        session._turn_counter = len(session.turns)

    if (
        session.turns
        and "messages" not in inspect(model).unloaded
        and isinstance(model.messages, list)
    ):
        assistant_messages = sorted(
            [m for m in model.messages if m.role == "assistant" and m.generated_sql],
            key=lambda item: item.created_at,
        )
        remaining = assistant_messages.copy()

        for turn in session.turns:
            if not turn.final_sql:
                continue

            matched: MessageModel | None = None
            for idx, message in enumerate(remaining):
                if message.generated_sql == turn.final_sql:
                    matched = message
                    del remaining[idx]
                    break

            if matched is None and remaining:
                matched = remaining.pop(0)

            if matched is not None:
                turn.assistant_message_id = str(matched.id)
                turn.assistant_is_few_shot = bool(matched.is_few_shot)
                turn.tables_used = matched.tables_used or []

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


def _map_turn(model: TurnModel) -> Turn:
    clarifications = [_map_clarification(c) for c in model.clarifications]
    return Turn(
        turn_id=model.turn_id,
        question=model.question,
        status=TurnStatus(model.status),
        clarifications=clarifications,
        final_sql=model.final_sql,
        validation_passed=model.validation_passed,
        error=model.error,
        chart_plan=model.chart_plan,
        chart_reasoning=model.chart_reasoning,
        created_at=model.created_at,
    )


def _map_clarification(model: ClarificationModel) -> Clarification:
    return Clarification(questions=model.questions or [], answer=model.answer)
