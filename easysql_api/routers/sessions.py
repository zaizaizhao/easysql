from __future__ import annotations

import inspect
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from easysql_api.deps import SessionStoreType, get_session_store_dep
from easysql_api.models.query import BranchRequest, MessageRequest
from easysql_api.models.session import (
    SessionDetail,
    SessionInfo,
    SessionList,
)
from easysql_api.models.turn import TurnInfo


class CreateSessionRequest(BaseModel):
    db_name: str | None = None


from easysql_api.services.query_service import get_query_service

router = APIRouter()


async def call_store_method(
    store: SessionStoreType, method_name: str, *args: Any, **kwargs: Any
) -> Any:
    method = getattr(store, method_name)
    result = method(*args, **kwargs)
    if inspect.iscoroutine(result):
        return await result
    return result


@router.post("/sessions", response_model=SessionInfo)
async def create_session(
    request: CreateSessionRequest,
) -> SessionInfo:
    service = get_query_service()
    session = service.create_session(db_name=request.db_name)
    return SessionInfo(
        session_id=session.session_id,
        db_name=session.db_name,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
        question_count=0,
    )


@router.get("/sessions", response_model=SessionList)
async def list_sessions(
    store: Annotated[SessionStoreType, Depends(get_session_store_dep)],
    limit: int = 100,
    offset: int = 0,
) -> SessionList:
    sessions = await call_store_method(store, "list_all", limit=limit, offset=offset)
    total = await call_store_method(store, "count")

    session_infos = [
        SessionInfo(
            session_id=s.session_id,
            db_name=s.db_name,
            status=s.status,
            created_at=s.created_at,
            updated_at=s.updated_at,
            question_count=len(s.turns),
            title=s.turns[0].question if s.turns else None,
        )
        for s in sessions
    ]

    return SessionList(sessions=session_infos, total=total)


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    store: Annotated[SessionStoreType, Depends(get_session_store_dep)],
) -> SessionDetail:
    session = await call_store_method(store, "get", session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    turns = [TurnInfo.from_dataclass(t) for t in session.turns]

    return SessionDetail(
        session_id=session.session_id,
        db_name=session.db_name,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
        raw_query=session.raw_query,
        generated_sql=session.generated_sql,
        validation_passed=session.validation_passed,
        turns=turns,
        state=session.state,
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    store: Annotated[SessionStoreType, Depends(get_session_store_dep)],
) -> dict:
    deleted = await call_store_method(store, "delete", session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"message": "Session deleted", "session_id": session_id}


@router.post("/sessions/{session_id}/message")
async def send_message(
    session_id: str,
    request: MessageRequest,
    store: Annotated[SessionStoreType, Depends(get_session_store_dep)],
):
    from easysql_api.models.query import QueryStatus

    session = await call_store_method(store, "get", session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    service = get_query_service()

    is_first_message = session.status == QueryStatus.PENDING

    if request.stream:
        import json

        async def generate():
            if is_first_message:
                async for event in service.stream_query(session, request.question):
                    yield f"data: {json.dumps(event)}\n\n"
            else:
                async for event in service.stream_follow_up_query(
                    session, request.question, parent_message_id=None
                ):
                    yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    if is_first_message:
        result = await service.execute_query(session, request.question)
    else:
        result = await service.follow_up_query(session, request.question, parent_message_id=None)
    return {"session_id": session_id, **result}


@router.post("/sessions/{session_id}/branch")
async def create_branch(
    session_id: str,
    request: BranchRequest,
    store: Annotated[SessionStoreType, Depends(get_session_store_dep)],
):
    session = await call_store_method(store, "get", session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    service = get_query_service()

    if request.stream:
        import json

        async def generate():
            async for event in service.stream_follow_up_query(
                session, request.question, parent_message_id=request.from_message_id
            ):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    result = await service.follow_up_query(
        session, request.question, parent_message_id=request.from_message_id
    )
    return {"session_id": session_id, "from_message_id": request.from_message_id, **result}
