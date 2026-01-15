from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from easysql_api.deps import get_session_store_dep
from easysql_api.models.session import (
    SessionInfo,
    SessionList,
    SessionDetail,
    MessageInfo,
)
from easysql_api.services.session_store import SessionStore

router = APIRouter()


@router.get("/sessions", response_model=SessionList)
async def list_sessions(
    store: Annotated[SessionStore, Depends(get_session_store_dep)],
    limit: int = 100,
    offset: int = 0,
) -> SessionList:
    sessions = store.list_all(limit=limit, offset=offset)

    session_infos = [
        SessionInfo(
            session_id=s.session_id,
            db_name=s.db_name,
            status=s.status,
            created_at=s.created_at,
            updated_at=s.updated_at,
            question_count=len(s.messages),
        )
        for s in sessions
    ]

    return SessionList(sessions=session_infos, total=store.count())


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    store: Annotated[SessionStore, Depends(get_session_store_dep)],
) -> SessionDetail:
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = [
        MessageInfo(
            role=m.get("role", "unknown"),
            content=m.get("content", ""),
            timestamp=m.get("timestamp", datetime.now(timezone.utc)),
        )
        for m in session.messages
    ]

    return SessionDetail(
        session_id=session.session_id,
        db_name=session.db_name,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
        raw_query=session.raw_query,
        generated_sql=session.generated_sql,
        validation_passed=session.validation_passed,
        messages=messages,
        state=session.state,
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    store: Annotated[SessionStore, Depends(get_session_store_dep)],
) -> dict:
    deleted = store.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"message": "Session deleted", "session_id": session_id}
