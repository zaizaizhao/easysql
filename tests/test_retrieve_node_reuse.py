from __future__ import annotations

from typing import Any

from easysql.llm.nodes.retrieve import RetrieveNode
from easysql.retrieval.schema_retrieval import RetrievalResult


class RecordingRetrievalService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def retrieve_databases(
        self,
        question: str,
        db_names: list[str],
        initial_tables_by_db: dict[str, list[dict[str, Any]]] | None = None,
    ) -> RetrievalResult:
        self.calls.append(
            {
                "question": question,
                "db_names": db_names,
                "initial_tables": (initial_tables_by_db or {}).get(db_names[0]),
            }
        )
        return RetrievalResult(tables=[])


def make_state(*, raw_query: str, clarified_query: str | None) -> dict[str, Any]:
    return {
        "raw_query": raw_query,
        "clarified_query": clarified_query,
        "db_name": "his",
        "schema_hint": {
            "tables": [
                {
                    "name": "patient",
                    "score": 0.9,
                    "chinese_name": "患者",
                    "description": "患者主表",
                    "key_columns": [],
                }
            ],
            "semantic_columns": [],
        },
    }


def test_reuses_hint_when_analyze_keeps_original_question() -> None:
    service = RecordingRetrievalService()
    node = RetrieveNode(service=service)  # type: ignore[arg-type]

    node(make_state(raw_query="查询患者", clarified_query="查询患者"))  # type: ignore[arg-type]

    assert service.calls[0]["initial_tables"] == [
        {
            "name": "patient",
            "score": 0.9,
            "chinese_name": "患者",
            "description": "患者主表",
        }
    ]


def test_retrieves_again_when_clarification_changes_question() -> None:
    service = RecordingRetrievalService()
    node = RetrieveNode(service=service)  # type: ignore[arg-type]

    node(
        make_state(
            raw_query="查询患者",
            clarified_query="查询本月门诊患者",
        )  # type: ignore[arg-type]
    )

    assert service.calls[0]["question"] == "查询本月门诊患者"
    assert service.calls[0]["initial_tables"] is None
