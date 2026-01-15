from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PipelineStatusEnum(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineRunRequest(BaseModel):
    db_names: list[str] | None = Field(
        default=None,
        description="Database names to process. If None, process all configured databases.",
    )
    extract: bool = Field(default=True)
    write_neo4j: bool = Field(default=True)
    write_milvus: bool = Field(default=True)
    drop_existing: bool = Field(default=False)


class PipelineStats(BaseModel):
    databases_processed: int = 0
    tables_extracted: int = 0
    columns_extracted: int = 0
    foreign_keys_extracted: int = 0
    neo4j_tables_written: int = 0
    neo4j_columns_written: int = 0
    neo4j_fks_written: int = 0
    milvus_tables_written: int = 0
    milvus_columns_written: int = 0
    errors: list[str] = Field(default_factory=list)


class PipelineRunResponse(BaseModel):
    task_id: str
    status: PipelineStatusEnum
    message: str


class PipelineStatus(BaseModel):
    status: PipelineStatusEnum
    task_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    stats: PipelineStats | None = None
    error: str | None = None
