"""Few-Shot examples API routes."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from easysql.config import get_settings
from easysql.embeddings.embedding_service import EmbeddingService
from easysql.readers.few_shot_reader import FewShotReader, FewShotResult
from easysql.repositories.milvus_repository import MilvusRepository
from easysql.utils.logger import get_logger
from easysql.writers.few_shot_writer import DuplicateExampleError, FewShotWriter
from easysql_api.deps import get_session_repository_dep
from easysql_api.domain.repositories.session_repository import SessionRepository
from easysql_api.models.few_shot import (
    FewShotCheckResponse,
    FewShotCreate,
    FewShotInfo,
    FewShotList,
    FewShotUpdate,
)

router = APIRouter()
logger = get_logger(__name__)
TURN_MESSAGE_ID_PATTERN = re.compile(
    r"^turn_([0-9a-fA-F-]{36})_(.+)$"
)


def get_milvus_repository() -> MilvusRepository:
    settings = get_settings()
    return MilvusRepository(
        uri=settings.milvus_uri,
        token=settings.milvus_token,
        collection_prefix=settings.milvus_collection_prefix,
    )


def get_few_shot_writer(
    repo: Annotated[MilvusRepository, Depends(get_milvus_repository)],
) -> FewShotWriter:
    settings = get_settings()
    embedding_service = EmbeddingService.from_settings(settings)
    return FewShotWriter(
        repository=repo,
        embedding_service=embedding_service,
        collection_name=settings.few_shot_collection_name,
    )


def get_few_shot_reader(
    repo: Annotated[MilvusRepository, Depends(get_milvus_repository)],
) -> FewShotReader:
    settings = get_settings()
    embedding_service = EmbeddingService.from_settings(settings)
    return FewShotReader(
        repository=repo,
        embedding_service=embedding_service,
        collection_name=settings.few_shot_collection_name,
    )


def _result_to_info(example: FewShotResult) -> FewShotInfo:
    """Convert a FewShotResult to FewShotInfo response model."""
    return FewShotInfo(
        id=example.id,
        db_name=example.db_name,
        question=example.question,
        sql=example.sql,
        tables_used=example.tables_used,
        explanation=example.explanation or None,
        message_id=example.message_id or None,
        created_at=example.created_at,
    )


async def _resolve_persisted_message_id(
    repository: SessionRepository,
    message_id: str | None,
) -> str | None:
    """Resolve turn-scoped message id to persisted assistant message id when possible."""
    if not message_id:
        return None

    if not message_id.startswith("turn_"):
        return message_id

    match = TURN_MESSAGE_ID_PATTERN.match(message_id)
    if not match:
        return message_id

    session_id, turn_id = match.groups()
    try:
        session = await repository.get(session_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "Failed resolving turn-scoped message id=%s: %s",
            message_id,
            exc,
        )
        return message_id

    if not session:
        return message_id

    turn = session.get_turn(turn_id)
    if not turn or not turn.assistant_message_id:
        return message_id

    return turn.assistant_message_id


async def _mark_related_message(
    repository: SessionRepository,
    message_id: str | None,
    *,
    is_few_shot: bool,
) -> None:
    if not message_id:
        return

    resolved_message_id = await _resolve_persisted_message_id(repository, message_id)
    if not resolved_message_id:
        return

    try:
        await repository.mark_as_few_shot(
            resolved_message_id,
            is_few_shot=is_few_shot,
        )
    except (ValueError, AttributeError) as exc:
        logger.debug(
            "Skip syncing message few-shot flag for message_id=%s: %s",
            resolved_message_id,
            exc,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed syncing message few-shot flag for message_id=%s: %s",
            resolved_message_id,
            exc,
        )


@router.post("/few-shot", response_model=FewShotInfo)
async def create_few_shot(
    request: FewShotCreate,
    writer: Annotated[FewShotWriter, Depends(get_few_shot_writer)],
    repository: Annotated[SessionRepository, Depends(get_session_repository_dep)],
) -> FewShotInfo:
    """Create a new few-shot example.

    Returns 409 Conflict if a similar example already exists.
    """
    writer.create_collection(drop_existing=False)
    resolved_message_id = await _resolve_persisted_message_id(repository, request.message_id)

    try:
        example_id = writer.insert(
            db_name=request.db_name,
            question=request.question,
            sql=request.sql,
            tables_used=request.tables_used,
            explanation=request.explanation,
            message_id=resolved_message_id,
            check_duplicate=True,
        )
    except DuplicateExampleError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Similar example already exists",
                "existing_id": e.existing_id,
                "similarity_score": e.similarity_score,
            },
        ) from e

    await _mark_related_message(repository, resolved_message_id, is_few_shot=True)

    return FewShotInfo(
        id=example_id,
        db_name=request.db_name,
        question=request.question,
        sql=request.sql,
        tables_used=request.tables_used,
        explanation=request.explanation,
        message_id=resolved_message_id,
        created_at=datetime.now(timezone.utc),
    )


@router.get("/few-shot", response_model=FewShotList)
async def list_few_shots(
    reader: Annotated[FewShotReader, Depends(get_few_shot_reader)],
    db_name: str = Query(..., description="Database name to filter by"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> FewShotList:
    """List all few-shot examples for a database with pagination."""
    examples = reader.list_by_db(db_name=db_name, limit=limit, offset=offset)
    total = reader.count_by_db(db_name=db_name)

    items = [_result_to_info(ex) for ex in examples]

    return FewShotList(items=items, total=total, db_name=db_name)


@router.get("/few-shot/by-message/{message_id}", response_model=FewShotCheckResponse)
async def check_message_few_shot(
    message_id: str,
    reader: Annotated[FewShotReader, Depends(get_few_shot_reader)],
) -> FewShotCheckResponse:
    """Check if a message has been saved as a few-shot example."""
    example = reader.get_by_message_id(message_id)

    if not example:
        return FewShotCheckResponse(is_few_shot=False)

    return FewShotCheckResponse(
        is_few_shot=True,
        example_id=example.id,
        example=_result_to_info(example),
    )


@router.get("/few-shot/{example_id}", response_model=FewShotInfo)
async def get_few_shot(
    example_id: str,
    reader: Annotated[FewShotReader, Depends(get_few_shot_reader)],
) -> FewShotInfo:
    """Get a specific few-shot example by ID."""
    example = reader.get_by_id(example_id)
    if not example:
        raise HTTPException(status_code=404, detail="Few-shot example not found")

    return _result_to_info(example)


@router.put("/few-shot/{example_id}", response_model=FewShotInfo)
async def update_few_shot(
    example_id: str,
    request: FewShotUpdate,
    writer: Annotated[FewShotWriter, Depends(get_few_shot_writer)],
    reader: Annotated[FewShotReader, Depends(get_few_shot_reader)],
) -> FewShotInfo:
    """Update an existing few-shot example.

    Only provided fields will be updated. Pass null to keep existing values.
    """
    # Check if example exists
    existing = reader.get_by_id(example_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Few-shot example not found")

    # Perform update
    success = writer.update(
        example_id=example_id,
        question=request.question,
        sql=request.sql,
        tables_used=request.tables_used,
        explanation=request.explanation,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update example")

    # Fetch updated record
    updated = reader.get_by_id(example_id)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to fetch updated example")

    return _result_to_info(updated)


@router.delete("/few-shot/{example_id}")
async def delete_few_shot(
    example_id: str,
    writer: Annotated[FewShotWriter, Depends(get_few_shot_writer)],
    reader: Annotated[FewShotReader, Depends(get_few_shot_reader)],
    repository: Annotated[SessionRepository, Depends(get_session_repository_dep)],
) -> dict:
    """Delete a few-shot example by ID."""
    existing = reader.get_by_id(example_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Few-shot example not found")

    success = writer.delete(example_id)
    if not success:
        raise HTTPException(status_code=404, detail="Few-shot example not found or delete failed")

    await _mark_related_message(repository, existing.message_id, is_few_shot=False)

    return {"message": "Few-shot example deleted", "id": example_id}
