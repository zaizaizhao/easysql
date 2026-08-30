"""Turn entities for conversation tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TurnStatus(str, Enum):
    """Status of a conversation turn."""

    IN_PROGRESS = "in_progress"
    AWAITING_CLARIFY = "awaiting_clarify"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Clarification:
    """A clarification exchange within a turn."""

    questions: list[str]
    answer: str | None = None


@dataclass
class Turn:
    """A single question-answer interaction unit."""

    turn_id: str
    question: str
    status: TurnStatus = TurnStatus.IN_PROGRESS
    clarifications: list[Clarification] = field(default_factory=list)
    final_sql: str | None = None
    primary_db: str | None = None
    validation_passed: bool | None = None
    error: str | None = None
    tables_used: list[str] = field(default_factory=list)
    assistant_message_id: str | None = None
    assistant_is_few_shot: bool = False
    chart_plan: dict[str, Any] | None = None
    chart_reasoning: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_clarification(self, questions: list[str]) -> Clarification:
        """Add a clarification request."""
        clarification = Clarification(questions=questions)
        self.clarifications.append(clarification)
        self.status = TurnStatus.AWAITING_CLARIFY
        return clarification

    def answer_clarification(self, answer: str) -> None:
        """Record the user's answer to the latest clarification."""
        if self.clarifications and self.clarifications[-1].answer is None:
            self.clarifications[-1].answer = answer
            self.status = TurnStatus.IN_PROGRESS

    def complete(
        self,
        sql: str | None,
        validation_passed: bool | None,
        primary_db: str | None = None,
    ) -> None:
        """Mark this turn as completed."""
        self.final_sql = sql
        self.primary_db = primary_db
        self.validation_passed = validation_passed
        self.status = TurnStatus.COMPLETED

    def fail(self, error: str) -> None:
        """Mark this turn as failed."""
        self.final_sql = None
        self.validation_passed = False
        self.error = error
        self.status = TurnStatus.FAILED
