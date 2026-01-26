"""Few-Shot API data models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FewShotCreate(BaseModel):
    """Request to create a new few-shot example."""

    db_name: str = Field(..., description="Database name for isolation")
    question: str = Field(..., description="Natural language question")
    sql: str = Field(..., description="SQL query")
    tables_used: list[str] = Field(default_factory=list, description="Tables used in query")
    explanation: str | None = Field(default=None, description="Optional explanation")
    message_id: str | None = Field(default=None, description="Related message ID")


class FewShotUpdate(BaseModel):
    """Request to update an existing few-shot example."""

    question: str | None = Field(default=None, description="Updated question")
    sql: str | None = Field(default=None, description="Updated SQL query")
    tables_used: list[str] | None = Field(default=None, description="Updated tables list")
    explanation: str | None = Field(default=None, description="Updated explanation")


class FewShotInfo(BaseModel):
    """Few-shot example information."""

    id: str
    db_name: str
    question: str
    sql: str
    tables_used: list[str]
    explanation: str | None
    message_id: str | None
    created_at: datetime


class FewShotList(BaseModel):
    """List of few-shot examples."""

    items: list[FewShotInfo]
    total: int
    db_name: str


class FewShotCheckResponse(BaseModel):
    """Response for checking if a message is saved as few-shot."""

    is_few_shot: bool
    example_id: str | None = None
    example: FewShotInfo | None = None
