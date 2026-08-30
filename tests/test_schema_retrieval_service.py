"""Offline unit tests for SchemaRetrievalService orchestration.

Uses fake Milvus/Neo4j readers to pin down the retrieval contract:
- db_name is passed through to every Milvus search (cross-db isolation)
- FK-expanded tables are scored in ONE batched call (no N+1)
- bridge tables are protected via must_keep, provenance is reported
- empty db-filtered recall fails closed without leaking another database
"""

from easysql.retrieval.schema_retrieval import RetrievalConfig, SchemaRetrievalService


class FakeMilvusReader:
    def __init__(self, tables_by_db=None, unfiltered_tables=None):
        # {db_name: [(table, score), ...]}
        self._tables_by_db = tables_by_db or {}
        self._unfiltered = unfiltered_tables or []
        self.search_tables_calls = []
        self.search_columns_calls = []

    def search_tables(self, query, top_k=10, db_name=None, table_filter=None, filter_expr=None):
        self.search_tables_calls.append(
            {
                "query": query,
                "top_k": top_k,
                "db_name": db_name,
                "table_filter": list(table_filter) if table_filter else None,
            }
        )
        if table_filter:
            return [
                {
                    "table_name": t,
                    "database_name": db_name,
                    "chinese_name": None,
                    "description": None,
                    "score": 0.5,
                }
                for t in table_filter
            ][:top_k]
        if db_name is not None:
            rows = self._tables_by_db.get(db_name, [])
        else:
            rows = self._unfiltered
        return [
            {
                "table_name": t,
                "database_name": db_name,
                "chinese_name": None,
                "description": None,
                "score": s,
            }
            for t, s in rows
        ][:top_k]

    def search_columns(self, query, top_k=20, db_name=None, table_filter=None):
        self.search_columns_calls.append(
            {
                "query": query,
                "top_k": top_k,
                "db_name": db_name,
                "table_filter": list(table_filter) if table_filter else None,
            }
        )
        return []


class FakeNeo4jReader:
    def __init__(self, expansion_extra=None, bridges=None):
        self._expansion_extra = expansion_extra or []
        self._bridges = bridges or []
        self.find_bridge_calls = 0

    def expand_with_related_tables(self, table_names, max_depth=1, db_name=None):
        return list(table_names) + [t for t in self._expansion_extra if t not in table_names]

    def find_bridge_tables(self, high_score_tables, max_hops=3, db_name=None):
        self.find_bridge_calls += 1
        return [b for b in self._bridges if b not in high_score_tables]

    def get_fk_target_tables(self, table_names, db_name=None):
        return []

    def get_table_columns(self, table_names, db_name=None):
        return {t: [] for t in table_names}

    def find_join_paths_for_tables(self, tables, max_hops=5, db_name=None):
        return []


def make_service(milvus, neo4j, **config_overrides):
    defaults = {
        "search_top_k": 5,
        "expand_fk": True,
        "semantic_filter_enabled": True,
        "semantic_threshold": 0.4,
        "semantic_min_tables": 1,
        "bridge_protection_enabled": True,
        "llm_filter_enabled": False,
    }
    defaults.update(config_overrides)
    return SchemaRetrievalService(
        milvus_reader=milvus,
        neo4j_reader=neo4j,
        config=RetrievalConfig(**defaults),
    )


class TestDbIsolation:
    def test_db_name_reaches_every_milvus_search(self):
        milvus = FakeMilvusReader(tables_by_db={"his": [("patient", 0.9), ("prescription", 0.8)]})
        service = make_service(milvus, FakeNeo4jReader(expansion_extra=["visit"]))

        service.retrieve(question="查询患者处方", db_name="his")

        assert milvus.search_tables_calls[0]["db_name"] == "his"
        assert all(c["db_name"] == "his" for c in milvus.search_tables_calls)
        assert milvus.search_columns_calls[0]["db_name"] == "his"

    def test_empty_filtered_recall_fails_closed(self):
        milvus = FakeMilvusReader(
            tables_by_db={"empty_db": []},
            unfiltered_tables=[("patient", 0.9), ("prescription", 0.8)],
        )
        service = make_service(milvus, FakeNeo4jReader())

        result = service.retrieve(question="q", db_name="empty_db")

        assert result.stats.get("db_filter_fallback") is None
        assert result.tables == []
        assert milvus.search_tables_calls[0]["db_name"] == "empty_db"
        assert len(milvus.search_tables_calls) == 1


class TestBatchedRescore:
    def test_fk_expanded_tables_scored_in_single_call(self):
        milvus = FakeMilvusReader(tables_by_db={"his": [("patient", 0.9), ("prescription", 0.8)]})
        service = make_service(
            milvus,
            FakeNeo4jReader(expansion_extra=["visit", "dept", "ward"]),
        )

        service.retrieve(question="q", db_name="his")

        # exactly 2 table searches: main recall + ONE batched rescore
        assert len(milvus.search_tables_calls) == 2
        batch = milvus.search_tables_calls[1]
        assert sorted(batch["table_filter"]) == ["dept", "visit", "ward"]
        assert batch["top_k"] == 3

    def test_no_rescore_call_when_nothing_expanded(self):
        milvus = FakeMilvusReader(tables_by_db={"his": [("patient", 0.9), ("solo", 0.8)]})
        service = make_service(milvus, FakeNeo4jReader())

        service.retrieve(question="q", db_name="his")

        assert len(milvus.search_tables_calls) == 1


class TestProvenance:
    def test_bridge_tables_are_looked_up_once(self):
        milvus = FakeMilvusReader(tables_by_db={"his": [("patient", 0.9), ("prescription", 0.8)]})
        neo4j = FakeNeo4jReader(bridges=["bridge_tbl"])
        service = make_service(milvus, neo4j)

        service.retrieve(question="q", db_name="his")

        assert neo4j.find_bridge_calls == 1

    def test_stats_report_table_provenance(self):
        milvus = FakeMilvusReader(tables_by_db={"his": [("patient", 0.9), ("prescription", 0.8)]})
        service = make_service(
            milvus,
            FakeNeo4jReader(expansion_extra=["visit"], bridges=["bridge_tbl"]),
        )

        result = service.retrieve(question="q", db_name="his")

        prov = result.stats["provenance"]
        assert prov["patient"] == "vector_recall"
        assert prov["prescription"] == "vector_recall"
        assert prov["visit"] == "fk_expansion"
        assert prov["bridge_tbl"] == "bridge"

    def test_bridge_tables_survive_semantic_filter(self):
        milvus = FakeMilvusReader(tables_by_db={"his": [("patient", 0.9), ("prescription", 0.8)]})
        service = make_service(
            milvus,
            FakeNeo4jReader(bridges=["bridge_tbl"]),
            semantic_threshold=0.99,
        )

        result = service.retrieve(question="q", db_name="his")

        # bridge table has no semantic score at all, yet must survive filtering
        assert "bridge_tbl" in result.tables

    def test_schema_hint_provenance(self):
        milvus = FakeMilvusReader()
        service = make_service(milvus, FakeNeo4jReader(), expand_fk=False)

        result = service.retrieve(
            question="q",
            db_name="his",
            initial_tables=[
                {"name": "patient", "score": 0.9, "chinese_name": None, "description": None}
            ],
        )

        assert result.stats["provenance"]["patient"] == "schema_hint"
        # hint reuse must not trigger any Milvus table search
        assert milvus.search_tables_calls == []
