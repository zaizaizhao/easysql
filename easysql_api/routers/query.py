from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from easysql_api.deps import get_query_service_dep
from easysql_api.models.query import (
    ContinueRequest,
    QueryRequest,
    QueryResponse,
    QueryStatus,
)
from easysql_api.services.query_service import QueryService

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def create_query(
    request: QueryRequest,
    service: Annotated[QueryService, Depends(get_query_service_dep)],
) -> QueryResponse | StreamingResponse:
    if request.session_id:
        session = await service.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session = await service.create_session(db_name=request.db_name)

    if request.stream:
        return StreamingResponse(
            _stream_generator(service, session, request.question),
            media_type="text/event-stream",
        )

    result = await service.execute_query(session, request.question)

    return QueryResponse(
        session_id=session.session_id,
        status=result.get("status", QueryStatus.FAILED),
        sql=result.get("sql"),
        validation_passed=result.get("validation_passed"),
        validation_error=result.get("validation_error"),
        clarification=result.get("clarification"),
        error=result.get("error"),
        message_id=result.get("message_id"),
        parent_message_id=result.get("parent_message_id"),
        thread_id=result.get("thread_id"),
    )


@router.post("/query/{session_id}/continue", response_model=QueryResponse)
async def continue_query(
    session_id: str,
    request: ContinueRequest,
    service: Annotated[QueryService, Depends(get_query_service_dep)],
) -> QueryResponse | StreamingResponse:
    session = await service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if request.stream:
        return StreamingResponse(
            _stream_continue_generator(service, session, request.answer, request.thread_id),
            media_type="text/event-stream",
        )

    result = await service.continue_conversation(session, request.answer, thread_id=request.thread_id)

    return QueryResponse(
        session_id=session.session_id,
        status=result.get("status", QueryStatus.FAILED),
        sql=result.get("sql"),
        validation_passed=result.get("validation_passed"),
        validation_error=result.get("validation_error"),
        clarification=result.get("clarification"),
        error=result.get("error"),
        message_id=result.get("message_id"),
        parent_message_id=result.get("parent_message_id"),
        thread_id=result.get("thread_id"),
    )


async def _stream_generator(service: QueryService, session, question: str):
    async for event in service.stream_query(session, question):
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _stream_continue_generator(
    service: QueryService, session, answer: str, thread_id: str | None
):
    async for event in service.stream_continue_conversation(session, answer, thread_id=thread_id):
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
