from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SessionInfo(BaseModel):
    session_id: str
    db_name: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    question_count: int = 0


class SessionList(BaseModel):
    sessions: list[SessionInfo]
    total: int


class MessageInfo(BaseModel):
    role: str
    content: str
    timestamp: datetime


class SessionDetail(BaseModel):
    session_id: str
    db_name: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    raw_query: str | None = None
    generated_sql: str | None = None
    validation_passed: bool | None = None
    messages: list[MessageInfo] = Field(default_factory=list)
    state: dict[str, Any] | None = None
