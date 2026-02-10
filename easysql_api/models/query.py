from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from easysql_api.domain.value_objects.query_status import QueryStatus


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    db_name: str | None = Field(default=None)
    session_id: str | None = Field(default=None)
    stream: bool = Field(default=False)


class ContinueRequest(BaseModel):
    answer: str = Field(..., min_length=1, max_length=1000)
    stream: bool = Field(default=False)
    thread_id: str | None = Field(default=None, description="Thread ID for branch isolation")


class MessageRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    stream: bool = Field(default=False)
    parent_message_id: str | None = Field(default=None, description="Parent message ID")
    thread_id: str | None = Field(default=None, description="Thread ID for branch isolation")


class BranchRequest(BaseModel):
    from_message_id: str = Field(..., description="Message ID to branch from")
    question: str = Field(..., min_length=1, max_length=2000)
    stream: bool = Field(default=False)
    thread_id: str | None = Field(default=None, description="Parent thread ID for branching")


class ForkSessionRequest(BaseModel):
    from_message_id: str | None = Field(default=None, description="Source assistant message ID")
    thread_id: str | None = Field(default=None, description="Source thread ID for branching")
    turn_ids: list[str] = Field(default_factory=list, description="Ordered turn IDs to clone")


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
    message_id: str | None = None
    parent_message_id: str | None = None
    thread_id: str | None = None


class StreamEvent(BaseModel):
    event: str
    data: dict[str, Any]
