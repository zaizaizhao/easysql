from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import easysql.llm.tools.agent_tools as agent_tools_module
from easysql.llm.tools.agent_tools import (
    ExecuteSqlTool,
    SubmitFinalSqlTool,
    create_agent_tools,
)


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


class _Executor:
    def __init__(self) -> None:
        self.planned: list[Any] = []
        self.executed: list[Any] = []

    def validate(self, request: Any) -> SimpleNamespace:
        self.planned.append(request)
        return SimpleNamespace(success=True, error=None)

    def execute(self, request: Any) -> SimpleNamespace:
        self.executed.append(request)
        return SimpleNamespace(success=True, error=None)


def _patch_scope(monkeypatch: Any) -> None:
    monkeypatch.setattr(agent_tools_module, "DatabaseScope", _DatabaseScope)
    monkeypatch.setattr(agent_tools_module, "get_settings", lambda: SimpleNamespace())


def test_agent_exposes_only_final_submission_and_schema_search(monkeypatch: Any) -> None:
    _patch_scope(monkeypatch)

    tools = create_agent_tools(db_names=_Scope.names)

    assert [tool.name for tool in tools] == ["submit_final_sql", "search_objects"]


def test_candidate_check_uses_explain_but_final_submission_executes_limit_one(
    monkeypatch: Any,
) -> None:
    _patch_scope(monkeypatch)
    executor = _Executor()
    monkeypatch.setattr(agent_tools_module, "_get_federated_executor", lambda: executor)
    candidate = ExecuteSqlTool(db_names=_Scope.names, default_primary_db="emr_demo")
    final = SubmitFinalSqlTool(db_names=_Scope.names, default_primary_db="emr_demo")

    assert candidate._run("SELECT * FROM public.patient", "emr_demo").startswith("SUCCESS")
    assert final._run("SELECT * FROM public.patient", "emr_demo").startswith("SUCCESS")

    assert len(executor.planned) == 1
    assert len(executor.executed) == 1
    assert executor.planned[0].sql.endswith("LIMIT 1")
    assert executor.executed[0].sql.endswith("LIMIT 1")
