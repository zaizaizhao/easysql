"""Message models for session-level conversation tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Message:
    message_id: str
    session_id: str
    thread_id: str
    parent_id: str | None
    role: str
    content: str | None = None
    generated_sql: str | None = None
    tables_used: list[str] = field(default_factory=list)
    validation_passed: bool | None = None
    user_answer: str | None = None
    clarification_questions: list[str] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "thread_id": self.thread_id,
            "parent_id": self.parent_id,
            "role": self.role,
            "content": self.content,
            "generated_sql": self.generated_sql,
            "tables_used": self.tables_used,
            "validation_passed": self.validation_passed,
            "user_answer": self.user_answer,
            "clarification_questions": self.clarification_questions,
            "created_at": self.created_at.isoformat(),
        }
