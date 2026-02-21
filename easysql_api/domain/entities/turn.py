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

    def complete(self, sql: str | None, validation_passed: bool | None) -> None:
        """Mark this turn as completed."""
        self.final_sql = sql
        self.validation_passed = validation_passed
        self.status = TurnStatus.COMPLETED

    def fail(self, error: str) -> None:
        """Mark this turn as failed."""
        self.error = error
        self.status = TurnStatus.FAILED


def turn_to_dict(turn: Turn) -> dict[str, Any]:
    """Convert a Turn to a dictionary for storage."""
    return {
        "turn_id": turn.turn_id,
        "question": turn.question,
        "status": turn.status.value,
        "clarifications": [
            {"questions": c.questions, "answer": c.answer} for c in turn.clarifications
        ],
        "final_sql": turn.final_sql,
        "validation_passed": turn.validation_passed,
        "error": turn.error,
        "tables_used": turn.tables_used,
        "assistant_message_id": turn.assistant_message_id,
        "assistant_is_few_shot": turn.assistant_is_few_shot,
        "chart_plan": turn.chart_plan,
        "chart_reasoning": turn.chart_reasoning,
        "created_at": turn.created_at.isoformat(),
    }


def turn_from_dict(data: dict[str, Any]) -> Turn:
    """Reconstruct a Turn from a dictionary."""
    clarifications = [
        Clarification(questions=c["questions"], answer=c.get("answer"))
        for c in data.get("clarifications", [])
    ]
    created_at = data.get("created_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    elif created_at is None:
        created_at = datetime.now(timezone.utc)

    return Turn(
        turn_id=data["turn_id"],
        question=data["question"],
        status=TurnStatus(data.get("status", "in_progress")),
        clarifications=clarifications,
        final_sql=data.get("final_sql"),
        validation_passed=data.get("validation_passed"),
        error=data.get("error"),
        tables_used=data.get("tables_used", []) or [],
        assistant_message_id=data.get("assistant_message_id"),
        assistant_is_few_shot=bool(data.get("assistant_is_few_shot", False)),
        chart_plan=data.get("chart_plan"),
        chart_reasoning=data.get("chart_reasoning"),
        created_at=created_at,
    )
