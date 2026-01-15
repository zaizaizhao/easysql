from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QueryStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    COMPLETED = "completed"
    FAILED = "failed"


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    db_name: str | None = Field(default=None)
    stream: bool = Field(default=False)


class ContinueRequest(BaseModel):
    answer: str = Field(..., min_length=1, max_length=1000)


class ClarificationInfo(BaseModel):
    questions: list[str]


class QueryResponse(BaseModel):
    session_id: str
    status: QueryStatus
    sql: str | None = None
    validation_passed: bool | None = None
    validation_error: str | None = None
    clarification: ClarificationInfo | None = None
    error: str | None = None
    stats: dict[str, Any] | None = None


class StreamEvent(BaseModel):
    event: str
    data: dict[str, Any]
