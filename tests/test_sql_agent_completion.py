from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import AIMessage

import easysql.llm.nodes.sql_agent as sql_agent_module
from easysql.llm.nodes.sql_agent import SqlAgentNode


class _Scope:
    names = ["emr_demo", "pms_demo", "rvs_demo"]
    default_primary = "emr_demo"
    is_federated = True

    @staticmethod
    def require_primary(primary_db: str | None) -> SimpleNamespace:
        return SimpleNamespace(name=primary_db or "emr_demo")


class _DatabaseScope:
    @staticmethod
    def resolve(*args: Any, **kwargs: Any) -> _Scope:
        return _Scope()


class _LLM:
    def bind_tools(self, tools: list[Any]) -> _LLM:
        return self


class _Tool:
    def __init__(self, name: str, result: str) -> None:
        self.name = name
        self._result = result

    async def ainvoke(self, args: Any) -> str:
        return self._result


def _state() -> dict[str, Any]:
    return {
        "raw_query": "生成一条跨库 SQL",
        "db_name": "emr_demo",
        "db_names": ["emr_demo", "pms_demo", "rvs_demo"],
        "primary_db": None,
        "cached_context": {
            "system_prompt": "system",
            "user_prompt": "user",
            "total_tokens": 10,
        },
    }


def _node(max_iterations: int = 1, timeout_seconds: float = 5.0) -> SqlAgentNode:
    node = SqlAgentNode()
    node._settings = SimpleNamespace(
        llm=SimpleNamespace(
            agent_max_iterations=max_iterations,
            agent_timeout_seconds=timeout_seconds,
        )
    )
    return node


def _patch_runtime(monkeypatch: Any, tools: list[_Tool]) -> None:
    monkeypatch.setattr(sql_agent_module, "DatabaseScope", _DatabaseScope)
    monkeypatch.setattr(sql_agent_module, "get_llm", lambda *args, **kwargs: _LLM())
    monkeypatch.setattr(sql_agent_module, "get_agent_tools", lambda *args, **kwargs: tools)
    monkeypatch.setattr(sql_agent_module, "_get_langfuse_client", lambda: None)


def test_candidate_validation_is_not_promoted_to_final_sql(monkeypatch: Any) -> None:
    candidate_sql = "SELECT 1"
    node = _node()
    _patch_runtime(
        monkeypatch,
        [_Tool("validate_sql", "SUCCESS: SQL is valid and can be executed.")],
    )

    async def fake_stream(*args: Any, **kwargs: Any) -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "validate_sql",
                    "args": {"sql": candidate_sql, "primary_db": "emr_demo"},
                    "id": "candidate-1",
                }
            ],
        )

    monkeypatch.setattr(node, "_stream_llm_response", fake_stream)

    result = asyncio.run(node(_state()))

    assert result["generated_sql"] is None
    assert result["validation_passed"] is False
    assert "final" in result["error"].lower()


def test_successful_final_submission_stops_without_another_llm_round(monkeypatch: Any) -> None:
    final_sql = "SELECT * FROM public.patient LIMIT 50"
    node = _node(max_iterations=3)
    _patch_runtime(
        monkeypatch,
        [_Tool("submit_final_sql", "SUCCESS: SQL is valid and can be executed.")],
    )
    calls = 0

    async def fake_stream(*args: Any, **kwargs: Any) -> AIMessage:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise AssertionError("successful final submission must stop the loop")
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "submit_final_sql",
                    "args": {"sql": final_sql, "primary_db": "emr_demo"},
                    "id": "final-1",
                }
            ],
        )

    monkeypatch.setattr(node, "_stream_llm_response", fake_stream)

    result = asyncio.run(node(_state()))

    assert calls == 1
    assert result["generated_sql"] == final_sql
    assert result["primary_db"] == "emr_demo"
    assert result["validation_passed"] is True
    assert result["retry_count"] == 0


def test_agent_enforces_total_time_budget(monkeypatch: Any) -> None:
    node = _node(max_iterations=3, timeout_seconds=0.01)
    _patch_runtime(monkeypatch, [])

    async def slow_stream(*args: Any, **kwargs: Any) -> AIMessage:
        await asyncio.sleep(0.05)
        return AIMessage(content="SELECT 1")

    monkeypatch.setattr(node, "_stream_llm_response", slow_stream)

    result = asyncio.run(node(_state()))

    assert result["generated_sql"] is None
    assert result["validation_passed"] is False
    assert "time budget" in result["error"].lower()
