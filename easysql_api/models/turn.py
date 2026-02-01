"""API models for turn data."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from easysql_api.domain.entities.turn import Turn, TurnStatus


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
    def from_dataclass(cls, turn: Turn) -> "TurnInfo":
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
