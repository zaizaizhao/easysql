from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import easysql_api.services.query_service as query_service_module
from easysql_api.domain.entities.session import Session
from easysql_api.domain.entities.turn import TurnStatus
from easysql_api.domain.value_objects.query_status import QueryStatus
from easysql_api.services.query_service import QueryService


class _Repository:
    def __init__(self) -> None:
        self.statuses: list[QueryStatus] = []
        self.updated_fields: list[dict[str, Any]] = []

    async def update_status(self, session_id: str, status: QueryStatus) -> None:
        self.statuses.append(status)

    async def update_session_fields(self, session_id: str, **kwargs: Any) -> None:
        self.updated_fields.append(kwargs)

    async def save_turns(self, session_id: str, turns: list[Any]) -> None:
        return None


class _Graph:
    async def aget_state(self, config: Any) -> SimpleNamespace:
        return SimpleNamespace(next=())


class _Scope:
    @staticmethod
    def require_primary(primary_db: str | None) -> SimpleNamespace:
        return SimpleNamespace(name=primary_db or "emr_demo")


class _DatabaseScope:
    @staticmethod
    def resolve(*args: Any, **kwargs: Any) -> _Scope:
        return _Scope()


def test_unvalidated_result_marks_turn_and_session_failed(monkeypatch: Any) -> None:
    monkeypatch.setattr(query_service_module, "DatabaseScope", _DatabaseScope)
    repository = _Repository()
    service = QueryService(repository=repository)  # type: ignore[arg-type]
    session = Session(
        session_id="session-1",
        db_name="emr_demo",
        db_names=["emr_demo", "pms_demo", "rvs_demo"],
        status=QueryStatus.PROCESSING,
    )
    turn = session.create_turn("生成跨库 SQL")
    error = 'ERROR: column reference "mpi_id" is ambiguous'

    result = asyncio.run(
        service._process_result(
            _Graph(),
            session,
            {
                "generated_sql": "SELECT mpi_id FROM broken_query",
                "primary_db": "emr_demo",
                "validation_passed": False,
                "validation_result": {"valid": False, "error": error},
                "error": error,
            },
            {"configurable": {"thread_id": "session-1"}},
            turn,
            user_message_id=None,
            assistant_message_id=None,
            parent_message_id=None,
            thread_id="session-1",
            question=turn.question,
        )
    )

    assert result["status"] == QueryStatus.FAILED.value
    assert result["sql"] is None
    assert result["validation_passed"] is False
    assert result["validation_error"] == error
    assert session.status == QueryStatus.FAILED
    assert session.generated_sql is None
    assert session.validation_passed is False
    assert turn.status == TurnStatus.FAILED
    assert turn.final_sql is None
    assert turn.error == error
    assert repository.statuses[-1] == QueryStatus.FAILED


def test_valid_flag_without_sql_is_rejected(monkeypatch: Any) -> None:
    monkeypatch.setattr(query_service_module, "DatabaseScope", _DatabaseScope)
    repository = _Repository()
    service = QueryService(repository=repository)  # type: ignore[arg-type]
    session = Session(
        session_id="session-2",
        db_name="emr_demo",
        db_names=["emr_demo"],
        status=QueryStatus.PROCESSING,
    )
    turn = session.create_turn("生成 SQL")

    result = asyncio.run(
        service._process_result(
            _Graph(),
            session,
            {
                "generated_sql": None,
                "primary_db": "emr_demo",
                "validation_passed": True,
                "validation_result": {"valid": True},
                "error": None,
            },
            {"configurable": {"thread_id": "session-2"}},
            turn,
            user_message_id=None,
            assistant_message_id=None,
            parent_message_id=None,
            thread_id="session-2",
            question=turn.question,
        )
    )

    assert result["status"] == QueryStatus.FAILED.value
    assert result["sql"] is None
    assert result["validation_passed"] is False
    assert "without a validated final sql" in result["error"].lower()
    assert session.status == QueryStatus.FAILED
    assert turn.status == TurnStatus.FAILED
