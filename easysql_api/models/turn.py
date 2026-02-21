"""API models for turn data."""

from __future__ import annotations

from datetime import datetime
from typing import Any

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
    tables_used: list[str] = Field(default_factory=list)
    assistant_message_id: str | None = None
    assistant_is_few_shot: bool = False
    chart_plan: dict[str, Any] | None = None
    chart_reasoning: str | None = None
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
            tables_used=turn.tables_used,
            assistant_message_id=turn.assistant_message_id,
            assistant_is_few_shot=turn.assistant_is_few_shot,
            chart_plan=turn.chart_plan,
            chart_reasoning=turn.chart_reasoning,
            created_at=turn.created_at,
        )


class ChartPlanUpdateRequest(BaseModel):
    """API model for updating chart plan per turn."""

    chart_plan: dict[str, Any]
    chart_reasoning: str | None = None
