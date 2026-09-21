from __future__ import annotations

import asyncio
from types import SimpleNamespace

from google.adk.sessions import InMemorySessionService

from easysql.config import DatabaseConfig, Settings
from easysql.federation import DatabaseScope
from easysql_agentic import runtime as runtime_module
from easysql_agentic.runtime import AgentRuntime
from easysql_agentic.tools.context import ContextTools
from tests.agentic.fakes import FakeCatalog, FakeExecutor, ScriptedModel


def settings() -> Settings:
    return Settings(
        _env_file=None,
        databases={
            "emr": DatabaseConfig(
                name="emr",
                db_type="postgresql",
                host="localhost",
                port=5432,
                user="test",
                password="test",
                database="emr",
            )
        },
    )


def test_real_adk_runner_calls_context_tools_and_requires_final_submission(monkeypatch) -> None:
    config = settings()
    monkeypatch.setattr(runtime_module, "get_settings", lambda: config)
    scope = DatabaseScope.resolve(config, db_names=["emr"])
    executor = FakeExecutor()
    tools = ContextTools(scope, SimpleNamespace(), catalog=FakeCatalog(), executor=executor)
    model = ScriptedModel(
        responses=[
            {"tool": "get_table_schema", "args": {"table_id": "emr.public.patient"}},
            {
                "tool": "assess_context",
                "args": {
                    "sufficient": True,
                    "missing": [],
                    "evidence_ids": ["schema:emr.public.patient"],
                    "rationale": "ID field is present",
                },
            },
            {
                "tool": "submit_final_sql",
                "args": {"sql": "SELECT id FROM public.patient", "primary_db": "emr"},
            },
        ]
    )

    async def run():
        events = []

        async def emit(event):
            events.append(event)

        runtime = AgentRuntime(InMemorySessionService(), model)
        outcome = await runtime.run(
            user_id="user", thread_id="thread", question="患者 ID", tools=tools, emit=emit
        )
        assert outcome["status"] == "completed"
        assert outcome["validation_passed"] is True
        assert outcome["tables_used"] == ["emr.public.patient"]
        assert len(executor.requests) == 1
        assert executor.requests[0].sql.endswith("LIMIT 1")
        assert [
            event["data"]["tool"] for event in events if event["data"]["type"] == "tool_start"
        ] == ["get_table_schema", "assess_context", "submit_final_sql"]

    asyncio.run(run())


def test_text_only_sql_is_not_success_and_unknown_evidence_is_rejected(monkeypatch) -> None:
    config = settings()
    monkeypatch.setattr(runtime_module, "get_settings", lambda: config)
    tools = ContextTools(DatabaseScope.resolve(config, db_names=["emr"]), SimpleNamespace())

    async def run():
        async def emit(event):
            pass

        result = await tools.assess_context(True, [], ["invented"], "I think so")
        assert result["accepted"] is False
        runtime = AgentRuntime(
            InMemorySessionService(),
            ScriptedModel(responses=[{"text": "SELECT id FROM public.patient"}]),
        )
        outcome = await runtime.run(
            user_id="user", thread_id="thread", question="患者 ID", tools=tools, emit=emit
        )
        assert outcome["status"] == "failed"
        assert not outcome["validation_passed"]

    asyncio.run(run())


def test_clarification_tool_ends_real_adk_invocation(monkeypatch) -> None:
    config = settings()
    monkeypatch.setattr(runtime_module, "get_settings", lambda: config)
    tools = ContextTools(DatabaseScope.resolve(config, db_names=["emr"]), SimpleNamespace())

    async def run():
        async def emit(event):
            pass

        runtime = AgentRuntime(
            InMemorySessionService(),
            ScriptedModel(
                responses=[
                    {"tool": "ask_clarification", "args": {"questions": ["统计哪个时间范围？"]}}
                ]
            ),
        )
        outcome = await runtime.run(
            user_id="user", thread_id="thread", question="统计患者", tools=tools, emit=emit
        )
        assert outcome["status"] == "awaiting_clarify"
        assert outcome["clarification"]["questions"] == ["统计哪个时间范围？"]

    asyncio.run(run())
