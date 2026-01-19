"""
SQL Execution Request/Response Models.

Defines the API contract for the standalone SQL execution endpoint.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExecuteStatus(str, Enum):
    """Status of SQL execution."""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    FORBIDDEN = "forbidden"


class ExecuteRequest(BaseModel):
    """Request model for SQL execution.

    Attributes:
        sql: The SQL query to execute.
        db_name: Target database name.
        limit: Maximum number of rows to return (safety limit).
        timeout: Query timeout in seconds.
        allow_mutation: Whether to allow INSERT/UPDATE/DELETE statements.
    """

    sql: str = Field(..., min_length=1, max_length=50000, description="SQL query to execute")
    db_name: str = Field(..., min_length=1, description="Target database name")
    limit: int = Field(default=1000, ge=1, le=10000, description="Max rows to return")
    timeout: int = Field(default=30, ge=1, le=300, description="Query timeout in seconds")
    allow_mutation: bool = Field(
        default=False,
        description="Allow mutation statements (INSERT/UPDATE/DELETE). Disabled by default for safety.",
    )


class ExecuteResponse(BaseModel):
    """Response model for SQL execution.

    Attributes:
        status: Execution status.
        data: Query result rows as list of dicts.
        columns: Column names in order.
        row_count: Number of rows returned.
        affected_rows: Number of rows affected (for mutations).
        execution_time_ms: Query execution time in milliseconds.
        truncated: Whether result was truncated due to limit.
        error: Error message if execution failed.
    """

    status: ExecuteStatus
    data: list[dict[str, Any]] | None = None
    columns: list[str] | None = None
    row_count: int = 0
    affected_rows: int | None = None
    execution_time_ms: float | None = None
    truncated: bool = False
    error: str | None = None


class SqlCheckResult(BaseModel):
    """Result of SQL safety check.

    Attributes:
        safe: Whether the SQL is considered safe to execute.
        is_mutation: Whether the SQL contains mutation statements.
        statement_type: Detected statement type (SELECT, INSERT, etc.).
        warnings: List of warnings about the SQL.
    """

    safe: bool
    is_mutation: bool
    statement_type: str
    warnings: list[str] = Field(default_factory=list)
