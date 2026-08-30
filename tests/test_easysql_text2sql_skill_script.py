from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from types import ModuleType
from typing import Any

SCRIPT_PATH = (
    Path(__file__).parents[1] / "skills" / "easysql-text2sql" / "scripts" / "agent_tools.py"
)


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("easysql_text2sql_agent_tools", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_search_table_command_builds_scoped_payload(monkeypatch) -> None:
    module = load_script()
    calls: list[dict[str, Any]] = []

    def fake_request(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"matches": []}

    monkeypatch.setattr(module, "_request_json", fake_request)
    stdout = io.StringIO()

    exit_code = module.main(
        [
            "--base-url",
            "http://localhost:8000/api/v1",
            "search-tables",
            "--db",
            "emr",
            "--query",
            "放疗转诊",
            "--table",
            "service_request",
        ],
        stdout=stdout,
    )

    assert exit_code == 0
    assert json.loads(stdout.getvalue()) == {"matches": []}
    assert calls == [
        {
            "method": "POST",
            "path": "agent-tools/search-tables",
            "payload": {
                "db_name": "emr",
                "query": "放疗转诊",
                "top_k": 5,
                "table_names": ["service_request"],
            },
            "base_url": "http://localhost:8000/api/v1",
            "timeout": 30.0,
        }
    ]


def test_check_sql_marks_only_safe_non_mutation_select_as_read_only(monkeypatch) -> None:
    module = load_script()
    captured_payload: dict[str, Any] = {}

    def fake_request(**kwargs: Any) -> dict[str, Any]:
        captured_payload.update(kwargs["payload"])
        return {
            "safe": True,
            "is_mutation": False,
            "statement_type": "SELECT",
            "warnings": [],
        }

    monkeypatch.setattr(module, "_request_json", fake_request)
    stdout = io.StringIO()

    exit_code = module.main(
        [
            "check-sql",
            "--db",
            "emr",
            "--database",
            "pms",
            "--sql",
            "SELECT 1",
        ],
        stdout=stdout,
    )

    result = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert result["read_only"] is True
    assert captured_payload["primary_db"] == "emr"
    assert captured_payload["db_names"] == ["emr", "pms"]
    assert captured_payload["allow_mutation"] is False


def test_script_returns_structured_transport_error(monkeypatch) -> None:
    module = load_script()

    def fail(**_: Any) -> dict[str, Any]:
        raise module.ToolApiError("backend unavailable")

    monkeypatch.setattr(module, "_request_json", fail)
    stderr = io.StringIO()

    exit_code = module.main(["databases"], stderr=stderr)

    assert exit_code == 1
    assert json.loads(stderr.getvalue()) == {"error": "backend unavailable"}
