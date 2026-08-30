from __future__ import annotations

from easysql.retrieval.schema_retrieval import RetrievalConfig, SchemaRetrievalService


class FakeMilvusReader:
    def __init__(self) -> None:
        self.database_calls: list[str | None] = []

    def search_tables(
        self,
        query: str,
        top_k: int = 10,
        db_name: str | None = None,
        table_filter: list[str] | None = None,
        filter_expr: str | None = None,
    ) -> list[dict]:
        self.database_calls.append(db_name)
        return [
            {
                "table_name": "patient",
                "database_name": db_name,
                "schema_name": "public",
                "chinese_name": f"{db_name}患者",
                "description": None,
                "score": 0.9,
            }
        ]

    def search_columns(self, **_kwargs):
        return []


class FakeNeo4jReader:
    def get_fk_target_tables(self, table_names, db_name=None):
        return []

    def get_table_columns(self, table_names, db_name=None):
        return {
            table: [
                {
                    "name": "patient_id",
                    "data_type": "bigint",
                    "is_pk": True,
                    "is_fk": False,
                }
            ]
            for table in table_names
        }

    def find_join_paths_for_tables(self, tables, max_hops=5, db_name=None):
        return []


def test_retrieve_databases_qualifies_same_named_tables_without_collision() -> None:
    milvus = FakeMilvusReader()
    service = SchemaRetrievalService(
        milvus_reader=milvus,
        neo4j_reader=FakeNeo4jReader(),
        config=RetrievalConfig(
            expand_fk=False,
            semantic_filter_enabled=False,
            bridge_protection_enabled=False,
        ),
        database_schemas={"emr": "public", "pms": "public"},
    )

    result = service.retrieve_databases("患者", ["emr", "pms"])

    assert result.tables == ["emr.public.patient", "pms.public.patient"]
    assert set(result.table_columns) == {
        "emr.public.patient",
        "pms.public.patient",
    }
    assert result.table_metadata["emr.public.patient"]["database_name"] == "emr"
    assert result.table_metadata["pms.public.patient"]["database_name"] == "pms"
    assert milvus.database_calls == ["emr", "pms"]


def test_retrieve_databases_preserves_legacy_name_for_single_database() -> None:
    service = SchemaRetrievalService(
        milvus_reader=FakeMilvusReader(),
        neo4j_reader=FakeNeo4jReader(),
        config=RetrievalConfig(
            expand_fk=False,
            semantic_filter_enabled=False,
            bridge_protection_enabled=False,
        ),
    )

    result = service.retrieve_databases("患者", ["emr"])

    assert result.tables == ["patient"]
    assert list(result.table_columns) == ["patient"]
