from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from easysql_api.models.turn import TurnInfo


class SessionInfo(BaseModel):
    session_id: str
    db_name: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    question_count: int = 0
    title: str | None = None


class SessionList(BaseModel):
    sessions: list[SessionInfo]
    total: int


class SessionDetail(BaseModel):
    session_id: str
    db_name: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    raw_query: str | None = None
    generated_sql: str | None = None
    validation_passed: bool | None = None
    turns: list[TurnInfo] = Field(default_factory=list)
    state: dict[str, Any] | None = None
