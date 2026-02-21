from __future__ import annotations

import asyncio
from typing import Any

from easysql_api.domain.entities.session import Session
from easysql_api.domain.value_objects.query_status import QueryStatus
from easysql_api.services.query_service import QueryService


class FakeRepository:
    async def update_status(self, session_id: str, status: QueryStatus) -> None:
        return None

    async def update_session_fields(self, session_id: str, **kwargs: Any) -> None:
        return None

    async def save_turns(self, session_id: str, turns: list[Any]) -> None:
        return None


class ReplacementGraph:
    async def ainvoke(self, input_state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        return {"generated_sql": "SELECT 1", "validation_passed": True}


class SwitchingGraph:
    def __init__(self, service: QueryService):
        self._service = service

    async def ainvoke(self, input_state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        self._service._graph = ReplacementGraph()
        return {"generated_sql": "SELECT 1", "validation_passed": True}


def test_execute_query_uses_pinned_graph_reference() -> None:
    service = QueryService(repository=FakeRepository())  # type: ignore[arg-type]
    first_graph = SwitchingGraph(service)
    service._graph = first_graph

    seen: dict[str, Any] = {}

    async def fake_process_result(
        self: QueryService,
        graph: Any,
        session: Session,
        result: dict[str, Any],
        config: dict[str, Any],
        turn: Any,
        *,
        user_message_id: str | None,
        assistant_message_id: str | None,
        parent_message_id: str | None,
        thread_id: str,
        question: str,
    ) -> dict[str, Any]:
        seen["graph"] = graph
        return {"status": QueryStatus.COMPLETED.value, "sql": "SELECT 1"}

    service._process_result = fake_process_result.__get__(service, QueryService)  # type: ignore[assignment]

    session = Session(session_id="session-1", db_name="test_db")
    result = asyncio.run(service.execute_query(session, "test query"))

    assert result["status"] == QueryStatus.COMPLETED.value
    assert seen["graph"] is first_graph
