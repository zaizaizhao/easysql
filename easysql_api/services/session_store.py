from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, Union, runtime_checkable

from easysql_api.models.query import QueryStatus
from easysql_api.models.message import Message
from easysql_api.models.turn import Turn


@runtime_checkable
class SessionProtocol(Protocol):
    """Protocol for session objects (both Session and PgSession)."""

    session_id: str
    db_name: str | None
    status: QueryStatus
    created_at: datetime
    updated_at: datetime
    turns: list[Turn]
    messages: dict[str, Message]

    def create_turn(self, question: str) -> Turn: ...
    def get_current_turn(self) -> Turn | None: ...
    def get_turn(self, turn_id: str) -> Turn | None: ...


SessionT = TypeVar("SessionT", bound=SessionProtocol)

if TYPE_CHECKING:
    from easysql_api.services.pg_session_store import PgSessionStore

SessionStoreType = Union["SessionStore", "PgSessionStore"]


@dataclass
class Session:
    session_id: str
    db_name: str | None = None
    status: QueryStatus = QueryStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_query: str | None = None
    generated_sql: str | None = None
    validation_passed: bool | None = None
    clarification_questions: list[str] | None = None
    state: dict[str, Any] | None = None
    turns: list[Turn] = field(default_factory=list)
    messages: dict[str, Message] = field(default_factory=dict)
    _turn_counter: int = 0

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

    def add_message(self, message: Message) -> None:
        self.messages[message.message_id] = message


class SessionStore:
    def __init__(self, max_sessions: int = 1000):
        self._sessions: dict[str, Session] = {}
        self._max_sessions = max_sessions
        self._lock = threading.Lock()

    def create(self, session_id: str, db_name: str | None = None) -> Session:
        with self._lock:
            if len(self._sessions) >= self._max_sessions:
                self._evict_oldest()

            session = Session(session_id=session_id, db_name=db_name)
            self._sessions[session_id] = session
            return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def update(self, session_id: str, **kwargs: Any) -> Session | None:
        session = self._sessions.get(session_id)
        if session:
            for key, value in kwargs.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            session.touch()
        return session

    def update_status(self, session_id: str, status: QueryStatus) -> Session | None:
        return self.update(session_id, status=status)

    def update_session_fields(self, session_id: str, **kwargs: Any) -> Session | None:
        return self.update(session_id, **kwargs)

    def save_turns(self, session_id: str, turns: list[Turn]) -> Session | None:
        session = self._sessions.get(session_id)
        if session:
            session.turns = turns
            session.touch()
        return session

    def add_message(
        self,
        session_id: str,
        *,
        message_id: str,
        thread_id: str,
        role: str,
        content: str | None,
        parent_id: str | None = None,
        generated_sql: str | None = None,
        tables_used: list[str] | None = None,
        validation_passed: bool | None = None,
        user_answer: str | None = None,
        clarification_questions: list[str] | None = None,
    ) -> str:
        session = self._sessions.get(session_id)
        if not session:
            return message_id

        message = Message(
            message_id=message_id,
            session_id=session_id,
            thread_id=thread_id,
            parent_id=parent_id,
            role=role,
            content=content,
            generated_sql=generated_sql,
            tables_used=tables_used or [],
            validation_passed=validation_passed,
            user_answer=user_answer,
            clarification_questions=clarification_questions,
        )
        session.add_message(message)
        session.touch()
        return message_id

    def get_message(self, message_id: str) -> Message | None:
        for session in self._sessions.values():
            message = session.messages.get(message_id)
            if message:
                return message
        return None

    def delete(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    def list_all(self, limit: int = 100, offset: int = 0) -> list[Session]:
        sessions = sorted(
            self._sessions.values(),
            key=lambda s: s.updated_at,
            reverse=True,
        )
        return sessions[offset : offset + limit]

    def count(self) -> int:
        return len(self._sessions)

    def _evict_oldest(self) -> None:
        if not self._sessions:
            return
        oldest = min(self._sessions.values(), key=lambda s: s.updated_at)
        del self._sessions[oldest.session_id]


_default_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _default_store
    if _default_store is None:
        _default_store = SessionStore()
    return _default_store
