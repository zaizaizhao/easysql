from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from easysql_api.models.query import QueryStatus


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
    messages: list[dict[str, Any]] = field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)


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
