from __future__ import annotations

import uuid
import threading
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from easysql_api.deps import get_settings_dep
from easysql_api.models.pipeline import (
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineStatus,
    PipelineStatusEnum,
    PipelineStats,
)
from easysql.config import Settings
from easysql.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


class PipelineState:
    def __init__(self):
        self.status = PipelineStatusEnum.IDLE
        self.task_id: str | None = None
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.stats: PipelineStats | None = None
        self.error: str | None = None
        self._lock = threading.Lock()

    def start(self, task_id: str) -> None:
        with self._lock:
            self.status = PipelineStatusEnum.RUNNING
            self.task_id = task_id
            self.started_at = datetime.now(timezone.utc)
            self.completed_at = None
            self.stats = None
            self.error = None

    def complete(self, stats: PipelineStats) -> None:
        with self._lock:
            self.status = PipelineStatusEnum.COMPLETED
            self.completed_at = datetime.now(timezone.utc)
            self.stats = stats

    def fail(self, error: str) -> None:
        with self._lock:
            self.status = PipelineStatusEnum.FAILED
            self.completed_at = datetime.now(timezone.utc)
            self.error = error

    def to_status(self) -> PipelineStatus:
        return PipelineStatus(
            status=self.status,
            task_id=self.task_id,
            started_at=self.started_at,
            completed_at=self.completed_at,
            stats=self.stats,
            error=self.error,
        )


_pipeline_state = PipelineState()


def run_pipeline_task(
    task_id: str,
    settings: Settings,
    request: PipelineRunRequest,
) -> None:
    from easysql.pipeline.schema_pipeline import SchemaPipeline

    try:
        pipeline = SchemaPipeline(settings)

        databases = None
        if request.db_names:
            databases = [
                settings.databases[name] for name in request.db_names if name in settings.databases
            ]

        stats = pipeline.run(
            databases=databases,
            extract=request.extract,
            write_neo4j=request.write_neo4j,
            write_milvus=request.write_milvus,
            drop_existing=request.drop_existing,
        )

        pipeline_stats = PipelineStats(
            databases_processed=stats.databases_processed,
            tables_extracted=stats.tables_extracted,
            columns_extracted=stats.columns_extracted,
            foreign_keys_extracted=stats.foreign_keys_extracted,
            neo4j_tables_written=stats.neo4j_tables_written,
            neo4j_columns_written=stats.neo4j_columns_written,
            neo4j_fks_written=stats.neo4j_fks_written,
            milvus_tables_written=stats.milvus_tables_written,
            milvus_columns_written=stats.milvus_columns_written,
            errors=stats.errors,
        )

        _pipeline_state.complete(pipeline_stats)
        pipeline.close()

    except Exception as e:
        logger.error(f"Pipeline task {task_id} failed: {e}")
        _pipeline_state.fail(str(e))


@router.post("/pipeline/run", response_model=PipelineRunResponse)
async def run_pipeline(
    request: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> PipelineRunResponse:
    if _pipeline_state.status == PipelineStatusEnum.RUNNING:
        raise HTTPException(
            status_code=409,
            detail="Pipeline is already running",
        )

    task_id = str(uuid.uuid4())
    _pipeline_state.start(task_id)

    background_tasks.add_task(run_pipeline_task, task_id, settings, request)

    return PipelineRunResponse(
        task_id=task_id,
        status=PipelineStatusEnum.RUNNING,
        message="Pipeline started",
    )


@router.get("/pipeline/status", response_model=PipelineStatus)
async def get_pipeline_status() -> PipelineStatus:
    return _pipeline_state.to_status()


@router.get("/pipeline/databases")
async def list_databases(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> dict:
    databases = []
    for name, config in settings.databases.items():
        databases.append(
            {
                "name": name,
                "type": config.db_type,
                "host": config.host,
                "port": config.port,
                "database": config.database,
                "description": config.description,
            }
        )

    return {"databases": databases, "total": len(databases)}
