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

    async def update_status(self, session_id: str, status: QueryStatus) -> None:
        self.statuses.append(status)

    async def update_session_fields(self, session_id: str, **kwargs: Any) -> None:
        return None

    async def save_turns(self, session_id: str, turns: list[Any]) -> None:
        return None

    async def add_message(self, *args: Any, **kwargs: Any) -> None:
        return None


class _Scope:
    @staticmethod
    def require_primary(primary_db: str | None) -> SimpleNamespace:
        return SimpleNamespace(name=primary_db or "emr_demo")


class _DatabaseScope:
    @staticmethod
    def resolve(*args: Any, **kwargs: Any) -> _Scope:
        return _Scope()


class _SlowGraph:
    async def ainvoke(self, input_state: Any, config: Any) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        return {
            "generated_sql": "SELECT 1",
            "primary_db": "emr_demo",
            "validation_passed": True,
        }

    async def astream(self, input_state: Any, config: Any, stream_mode: Any):
        await asyncio.sleep(0.05)
        yield {
            "sql_agent": {
                "generated_sql": "SELECT 1",
                "primary_db": "emr_demo",
                "validation_passed": True,
            }
        }

    async def aget_state(self, config: Any) -> SimpleNamespace:
        return SimpleNamespace(
            next=(),
            values={
                "generated_sql": "SELECT 1",
                "primary_db": "emr_demo",
                "validation_passed": True,
            },
        )


def _service(monkeypatch: Any) -> tuple[QueryService, _Repository]:
    monkeypatch.setattr(query_service_module, "DatabaseScope", _DatabaseScope)
    monkeypatch.setattr(
        query_service_module,
        "get_settings",
        lambda: SimpleNamespace(llm=SimpleNamespace(query_timeout_seconds=0.01)),
    )
    repository = _Repository()
    service = QueryService(repository=repository)  # type: ignore[arg-type]
    service._graph = _SlowGraph()
    service._callbacks = []
    return service, repository


def _session(session_id: str) -> Session:
    return Session(
        session_id=session_id,
        db_name="emr_demo",
        db_names=["emr_demo", "pms_demo", "rvs_demo"],
    )


def test_non_stream_query_enforces_end_to_end_timeout(monkeypatch: Any) -> None:
    service, repository = _service(monkeypatch)
    session = _session("non-stream")

    result = asyncio.run(service.execute_query(session, "test"))

    assert result["status"] == QueryStatus.FAILED.value
    assert "time budget" in result["error"].lower()
    assert session.status == QueryStatus.FAILED
    assert session.turns[-1].status == TurnStatus.FAILED
    assert repository.statuses[-1] == QueryStatus.FAILED


def test_stream_query_enforces_end_to_end_timeout(monkeypatch: Any) -> None:
    service, repository = _service(monkeypatch)
    session = _session("stream")

    async def collect() -> list[dict[str, Any]]:
        return [event async for event in service.stream_query(session, "test")]

    events = asyncio.run(collect())

    assert events[-1]["event"] == "error"
    assert "time budget" in events[-1]["data"]["error"].lower()
    assert session.status == QueryStatus.FAILED
    assert session.turns[-1].status == TurnStatus.FAILED
    assert repository.statuses[-1] == QueryStatus.FAILED
