from __future__ import annotations

from typing import Any

from easysql.agent_tools.runtime import MilvusAgentSearchAdapter


class FakeEmbedding:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def encode(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.1, 0.2]


class FakeMilvusClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(self, **kwargs: Any) -> list[list[dict[str, Any]]]:
        self.calls.append(kwargs)
        output_fields = kwargs["output_fields"]
        if "column_name" in output_fields:
            entity = {
                "database_name": "emr",
                "schema_name": "clinical",
                "qualified_table_id": "emr.clinical.patient",
                "table_name": "patient",
                "column_name": "mpi_id",
                "chinese_name": "患者主索引",
                "data_type": "varchar",
                "is_pk": False,
                "is_fk": False,
            }
        else:
            entity = {
                "database_name": "emr",
                "schema_name": "clinical",
                "table_name": "patient",
                "chinese_name": "患者",
                "description": "patient master",
                "business_domain": "clinical",
            }
        return [[{"entity": entity, "distance": 0.92}]]


class FakeRepository:
    def __init__(self) -> None:
        self.client = FakeMilvusClient()
        self.table_collection = "test_table_embeddings"
        self.column_collection = "test_column_embeddings"


def test_milvus_adapter_enforces_database_and_table_filters() -> None:
    repository = FakeRepository()
    embedding = FakeEmbedding()
    adapter = MilvusAgentSearchAdapter(
        repository=repository,  # type: ignore[arg-type]
        embedding_service=embedding,  # type: ignore[arg-type]
    )

    matches = adapter.search_tables(
        "患者",
        top_k=3,
        db_name="emr",
        table_filter=["patient"],
    )

    assert embedding.queries == ["患者"]
    assert matches[0]["schema_name"] == "clinical"
    call = repository.client.calls[0]
    assert call["collection_name"] == "test_table_embeddings"
    assert 'database_name == "emr"' in call["filter"]
    assert 'table_name in ["patient"]' in call["filter"]
    assert call["limit"] == 3


def test_milvus_adapter_returns_database_metadata_for_column_search() -> None:
    repository = FakeRepository()
    adapter = MilvusAgentSearchAdapter(
        repository=repository,  # type: ignore[arg-type]
        embedding_service=FakeEmbedding(),  # type: ignore[arg-type]
    )

    matches = adapter.search_columns("统一患者标识", db_name="emr")

    assert matches == [
        {
            "database_name": "emr",
            "schema_name": "clinical",
            "qualified_table_id": "emr.clinical.patient",
            "table_name": "patient",
            "column_name": "mpi_id",
            "chinese_name": "患者主索引",
            "data_type": "varchar",
            "is_pk": False,
            "is_fk": False,
            "score": 0.92,
        }
    ]
