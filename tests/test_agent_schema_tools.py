from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from easysql.agent_tools import DatabaseNotConfiguredError, SchemaToolService
from easysql.agent_tools.runtime import get_schema_tool_service
from easysql_api.routers.agent_tools import router


@dataclass
class FakeDatabaseConfig:
    db_type: str = "postgresql"
    schema: str = "public"
    system_type: str = "EMR"
    description: str = "Electronic medical records"
    host: str = "private.example"
    user: str = "secret-user"
    password: str = "secret-password"
    dblink_connection_name: str | None = None

    def get_default_schema(self) -> str:
        return self.schema

    def get_dblink_connection_name(self) -> str:
        return self.dblink_connection_name or "emr_conn"


class FakeMilvus:
    def __init__(self) -> None:
        self.table_calls: list[dict[str, Any]] = []
        self.column_calls: list[dict[str, Any]] = []

    def search_tables(
        self,
        query: str,
        top_k: int = 10,
        db_name: str | None = None,
        table_filter: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self.table_calls.append(
            {
                "query": query,
                "top_k": top_k,
                "db_name": db_name,
                "table_filter": table_filter,
            }
        )
        return [
            {
                "database_name": "emr",
                "schema_name": "clinical",
                "table_name": "service_request",
                "description": "referrals",
                "score": 0.91,
            },
            {
                "database_name": "pms",
                "schema_name": "public",
                "table_name": "consent_record",
                "score": 0.99,
            },
            {
                "database_name": "emr",
                "schema_name": "clinical",
                "table_name": "patient",
                "score": 0.73,
            },
        ][:top_k]

    def search_columns(
        self,
        query: str,
        top_k: int = 20,
        db_name: str | None = None,
        table_filter: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self.column_calls.append(
            {
                "query": query,
                "top_k": top_k,
                "db_name": db_name,
                "table_filter": table_filter,
            }
        )
        return [
            {
                "database_name": "emr",
                "schema_name": "clinical",
                "table_name": "patient",
                "column_name": "mpi_id",
                "data_type": "varchar",
                "is_pk": False,
                "is_fk": False,
                "score": 0.88,
            },
            {
                "database_name": "pms",
                "table_name": "portal_account",
                "column_name": "mpi_id",
                "score": 0.95,
            },
        ][:top_k]


class FakeNeo4j:
    def __init__(self) -> None:
        self.schema_calls: list[tuple[list[str], str | None]] = []
        self.expand_calls: list[tuple[list[str], int, str | None]] = []
        self.path_calls: list[tuple[list[str], int, str | None]] = []

    def get_table_columns(
        self,
        table_names: list[str],
        db_name: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        self.schema_calls.append((table_names, db_name))
        return {
            "patient": [
                {
                    "name": "patient_id",
                    "data_type": "bigint",
                    "is_pk": True,
                    "is_fk": False,
                    "is_nullable": False,
                    "ordinal_position": 1,
                },
                {
                    "name": "mpi_id",
                    "data_type": "varchar",
                    "is_pk": False,
                    "is_fk": False,
                    "is_nullable": False,
                    "ordinal_position": 2,
                },
            ]
        }

    def expand_with_related_tables(
        self,
        table_names: list[str],
        max_depth: int = 1,
        db_name: str | None = None,
    ) -> list[str]:
        self.expand_calls.append((table_names, max_depth, db_name))
        return [*table_names, "encounter", "patient", "encounter"]

    def find_join_paths_for_tables(
        self,
        tables: list[str],
        max_hops: int = 5,
        db_name: str | None = None,
    ) -> list[dict[str, Any]]:
        self.path_calls.append((tables, max_hops, db_name))
        edge = {
            "fk_table": "service_request",
            "fk_column": "encounter_id",
            "pk_table": "encounter",
            "pk_column": "encounter_id",
        }
        return [
            edge,
            edge,
            {
                "fk_table": "encounter",
                "fk_column": "patient_id",
                "pk_table": "patient",
                "pk_column": "patient_id",
            },
        ]


def make_service() -> tuple[SchemaToolService, FakeMilvus, FakeNeo4j]:
    milvus = FakeMilvus()
    neo4j = FakeNeo4j()
    settings = SimpleNamespace(
        databases={
            "emr": FakeDatabaseConfig(schema="clinical"),
            "pms": FakeDatabaseConfig(system_type="PMS", dblink_connection_name="pms_conn"),
        }
    )
    return (
        SchemaToolService(settings=settings, milvus=milvus, neo4j=neo4j),
        milvus,
        neo4j,
    )


def test_database_scope_is_credential_free() -> None:
    service, _, _ = make_service()

    result = service.describe_database_scope()

    assert result["total"] == 2
    assert result["databases"][0]["schema"] == "clinical"
    assert result["databases"][1]["dblink_connection_name"] == "pms_conn"
    serialized = json.dumps(result)
    assert "secret-password" not in serialized
    assert "secret-user" not in serialized
    assert "private.example" not in serialized


def test_table_search_is_database_scoped_and_fail_closed() -> None:
    service, milvus, _ = make_service()

    result = service.search_tables(db_name="EMR", query="  放疗转诊  ", top_k=5)

    assert milvus.table_calls == [
        {
            "query": "放疗转诊",
            "top_k": 5,
            "db_name": "emr",
            "table_filter": None,
        }
    ]
    assert [match["table"] for match in result["matches"]] == [
        "service_request",
        "patient",
    ]
    assert [match["rank"] for match in result["matches"]] == [1, 2]
    assert result["matches"][0]["schema"] == "clinical"


def test_column_search_passes_safe_table_filter_and_drops_other_database() -> None:
    service, milvus, _ = make_service()

    result = service.search_columns(
        db_name="emr",
        query="患者统一标识",
        table_names=["patient", "patient"],
    )

    assert milvus.column_calls[0]["table_filter"] == ["patient"]
    assert len(result["matches"]) == 1
    assert result["matches"][0]["column"] == "mpi_id"


def test_table_schema_reports_missing_tables() -> None:
    service, _, neo4j = make_service()

    result = service.get_table_schema(
        db_name="emr",
        table_names=["patient", "unknown_table"],
    )

    assert neo4j.schema_calls == [(["patient", "unknown_table"], "emr")]
    assert result["missing_tables"] == ["unknown_table"]
    assert result["tables"][0]["columns"][0]["is_primary_key"] is True


def test_expansion_separates_seed_and_added_tables() -> None:
    service, _, neo4j = make_service()

    result = service.expand_related_tables(
        db_name="emr",
        seed_tables=["service_request"],
        max_depth=2,
    )

    assert neo4j.expand_calls == [(["service_request"], 2, "emr")]
    assert result["seed_tables"] == ["service_request"]
    assert result["added_tables"] == ["encounter", "patient"]


def test_join_paths_are_directional_deduplicated_and_report_bridges() -> None:
    service, _, neo4j = make_service()

    result = service.find_join_paths(
        db_name="emr",
        table_names=["service_request", "patient"],
        max_hops=4,
    )

    assert neo4j.path_calls == [(["service_request", "patient"], 4, "emr")]
    assert len(result["edges"]) == 2
    assert result["bridge_tables"] == ["encounter"]
    assert result["edges"][0] == {
        "fk_table": "service_request",
        "fk_column": "encounter_id",
        "pk_table": "encounter",
        "pk_column": "encounter_id",
    }


def test_service_rejects_unknown_database_and_unsafe_identifier() -> None:
    service, _, _ = make_service()

    with pytest.raises(DatabaseNotConfiguredError):
        service.search_tables(db_name="billing", query="invoice")

    with pytest.raises(ValueError, match="unquoted"):
        service.get_table_schema(db_name="emr", table_names=['patient") MATCH (n)'])


def create_client(service: Any) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_schema_tool_service] = lambda: service
    return TestClient(app)


def test_router_exposes_independent_read_only_operations() -> None:
    service, _, _ = make_service()
    client = create_client(service)

    databases = client.get("/api/v1/agent-tools/databases")
    table_search = client.post(
        "/api/v1/agent-tools/search-tables",
        json={"db_name": "emr", "query": "放疗转诊", "top_k": 5},
    )
    schema = client.post(
        "/api/v1/agent-tools/table-schema",
        json={"db_name": "emr", "table_names": ["patient"]},
    )

    assert databases.status_code == 200
    assert table_search.status_code == 200
    assert table_search.json()["matches"][0]["table"] == "service_request"
    assert table_search.json()["elapsed_ms"] >= 0
    assert schema.status_code == 200


def test_router_enforces_request_budgets_before_calling_service() -> None:
    service, milvus, _ = make_service()
    client = create_client(service)

    response = client.post(
        "/api/v1/agent-tools/search-tables",
        json={"db_name": "emr", "query": "q", "top_k": 11},
    )

    assert response.status_code == 422
    assert milvus.table_calls == []


def test_router_returns_structured_unknown_database_error() -> None:
    service, _, _ = make_service()
    client = create_client(service)

    response = client.post(
        "/api/v1/agent-tools/search-columns",
        json={"db_name": "billing", "query": "invoice"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "DATABASE_NOT_CONFIGURED"


def test_router_does_not_leak_backend_exception_details() -> None:
    class BrokenService:
        def search_tables(self, **_: Any) -> dict[str, Any]:
            raise RuntimeError("password=do-not-leak")

    client = create_client(BrokenService())

    response = client.post(
        "/api/v1/agent-tools/search-tables",
        json={"db_name": "emr", "query": "q"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "RETRIEVAL_BACKEND_UNAVAILABLE"
    assert "do-not-leak" not in response.text


def test_main_app_registers_agent_tool_routes() -> None:
    from easysql_api.app import create_app

    paths = {route.path for route in create_app().routes}

    assert "/api/v1/agent-tools/search-tables" in paths
    assert "/api/v1/agent-tools/join-paths" in paths
