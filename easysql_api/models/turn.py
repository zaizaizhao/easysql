"""Turn-based conversation models for structured session data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TurnStatus(str, Enum):
    """Status of a conversation turn."""

    IN_PROGRESS = "in_progress"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Clarification:
    """A single clarification exchange within a turn."""

    questions: list[str]
    answer: str | None = None


@dataclass
class Turn:
    """A complete question-answer interaction unit.

    A Turn represents one user question and its resolution, including
    any clarification exchanges that occurred during processing.
    """

    turn_id: str
    question: str
    status: TurnStatus = TurnStatus.IN_PROGRESS
    clarifications: list[Clarification] = field(default_factory=list)
    final_sql: str | None = None
    validation_passed: bool | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_clarification(self, questions: list[str]) -> Clarification:
        """Add a new clarification request to this turn."""
        clarification = Clarification(questions=questions)
        self.clarifications.append(clarification)
        self.status = TurnStatus.AWAITING_CLARIFICATION
        return clarification

    def answer_clarification(self, answer: str) -> None:
        """Record the user's answer to the current clarification."""
        if self.clarifications and self.clarifications[-1].answer is None:
            self.clarifications[-1].answer = answer
            self.status = TurnStatus.IN_PROGRESS

    def complete(self, sql: str | None, validation_passed: bool | None) -> None:
        """Mark this turn as completed with the final SQL result."""
        self.final_sql = sql
        self.validation_passed = validation_passed
        self.status = TurnStatus.COMPLETED

    def fail(self, error: str) -> None:
        """Mark this turn as failed with an error message."""
        self.error = error
        self.status = TurnStatus.FAILED


class ClarificationInfo(BaseModel):
    """API model for clarification data."""

    questions: list[str]
    answer: str | None = None


class TurnInfo(BaseModel):
    """API model for turn data in responses."""

    turn_id: str
    question: str
    status: TurnStatus
    clarifications: list[ClarificationInfo] = Field(default_factory=list)
    final_sql: str | None = None
    validation_passed: bool | None = None
    error: str | None = None
    created_at: datetime

    @classmethod
    def from_dataclass(cls, turn: Turn) -> TurnInfo:
        """Convert a Turn dataclass to TurnInfo for API serialization."""
        return cls(
            turn_id=turn.turn_id,
            question=turn.question,
            status=turn.status,
            clarifications=[
                ClarificationInfo(questions=c.questions, answer=c.answer)
                for c in turn.clarifications
            ],
            final_sql=turn.final_sql,
            validation_passed=turn.validation_passed,
            error=turn.error,
            created_at=turn.created_at,
        )


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
        created_at=created_at,
    )
