"""SQLAlchemy ORM models for session persistence."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SessionModel(Base):
    __tablename__ = "easysql_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    db_name: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    raw_query: Mapped[str | None] = mapped_column(Text)
    generated_sql: Mapped[str | None] = mapped_column(Text)
    validation_passed: Mapped[bool | None] = mapped_column(Boolean)
    state: Mapped[dict | None] = mapped_column(JSONB)
    title: Mapped[str | None] = mapped_column(Text)

    turns: Mapped[list["TurnModel"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="TurnModel.position"
    )
    messages: Mapped[list["MessageModel"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class MessageModel(Base):
    __tablename__ = "easysql_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("easysql_sessions.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("easysql_messages.id", ondelete="SET NULL"), index=True
    )

    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)

    generated_sql: Mapped[str | None] = mapped_column(Text)
    tables_used: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    validation_passed: Mapped[bool | None] = mapped_column(Boolean)

    is_branch_point: Mapped[bool] = mapped_column(Boolean, default=False)
    checkpoint_id: Mapped[str | None] = mapped_column(String(100))
    token_count: Mapped[int | None] = mapped_column(Integer)

    is_few_shot: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    user_answer: Mapped[str | None] = mapped_column(Text)
    clarification_questions: Mapped[list | None] = mapped_column(JSONB)

    thread_id: Mapped[str | None] = mapped_column(Text, index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    root_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[SessionModel] = relationship(back_populates="messages")

    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_easysql_messages_role"),
    )


class TurnModel(Base):
    __tablename__ = "easysql_turns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("easysql_sessions.id", ondelete="CASCADE"), index=True
    )
    turn_id: Mapped[str] = mapped_column(String(20), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    final_sql: Mapped[str | None] = mapped_column(Text)
    validation_passed: Mapped[bool | None] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    chart_plan: Mapped[dict | None] = mapped_column(JSONB)
    chart_reasoning: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["SessionModel"] = relationship(back_populates="turns")
    clarifications: Mapped[list["ClarificationModel"]] = relationship(
        back_populates="turn", cascade="all, delete-orphan", order_by="ClarificationModel.position"
    )

    __table_args__ = (
        UniqueConstraint("session_id", "turn_id", name="uq_easysql_turns_session_turn_id"),
    )


class ClarificationModel(Base):
    __tablename__ = "easysql_turn_clarifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    turn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("easysql_turns.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    questions: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    turn: Mapped["TurnModel"] = relationship(back_populates="clarifications")


class FewShotMetaModel(Base):
    __tablename__ = "easysql_few_shot_meta"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("easysql_messages.id", ondelete="CASCADE")
    )
    db_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    sql: Mapped[str] = mapped_column(Text, nullable=False)
    tables_used: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    explanation: Mapped[str | None] = mapped_column(Text)
    milvus_id: Mapped[str | None] = mapped_column(String(256), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
