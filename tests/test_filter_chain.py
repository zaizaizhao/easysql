"""Offline unit tests for the retrieval filter chain.

Covers FilterChain / NoOpFilter / SemanticFilter / BridgeFilter with fake
readers — no Milvus/Neo4j required.
"""

from easysql.retrieval.base import FilterChain, FilterContext, NoOpFilter
from easysql.retrieval.bridge_filter import BridgeFilter
from easysql.retrieval.semantic_filter import SemanticFilter


class FakeNeo4jReader:
    """Fake Neo4jSchemaReader recording calls."""

    def __init__(self, bridges=None, neighbors=None):
        self._bridges = bridges or []
        self._neighbors = neighbors or []
        self.find_bridge_calls = []
        self.expand_calls = []

    def find_bridge_tables(self, high_score_tables, max_hops=3, db_name=None):
        self.find_bridge_calls.append(
            {"tables": list(high_score_tables), "max_hops": max_hops, "db_name": db_name}
        )
        return list(self._bridges)

    def expand_with_related_tables(self, table_names, max_depth=1, db_name=None):
        self.expand_calls.append(
            {"tables": list(table_names), "max_depth": max_depth, "db_name": db_name}
        )
        return list(table_names) + [n for n in self._neighbors if n not in table_names]


class TestNoOpFilter:
    def test_passthrough(self):
        context = FilterContext(question="q")
        result = NoOpFilter().filter(["a", "b"], context)
        assert result.tables == ["a", "b"]


class TestFilterChain:
    def test_executes_in_sequence(self):
        context = FilterContext(question="q", table_scores={"a": 0.9, "b": 0.1})
        chain = FilterChain([SemanticFilter(threshold=0.5, min_tables=1)])
        result = chain.execute(["a", "b"], context)
        assert result.tables == ["a"]
        assert "semantic" in result.stats["chain"]


class TestSemanticFilter:
    def test_removes_low_score_tables(self):
        context = FilterContext(
            question="q",
            original_tables=["a"],
            table_scores={"a": 0.9, "b": 0.1, "c": 0.2},
        )
        result = SemanticFilter(threshold=0.5, min_tables=1).filter(["a", "b", "c"], context)
        assert result.tables == ["a"]

    def test_must_keep_tables_survive_below_threshold(self):
        context = FilterContext(
            question="q",
            original_tables=["a"],
            must_keep={"b"},
            table_scores={"a": 0.9, "b": 0.1, "c": 0.1},
        )
        result = SemanticFilter(threshold=0.5, min_tables=1).filter(["a", "b", "c"], context)
        assert "b" in result.tables
        assert "c" not in result.tables

    def test_min_tables_backfills_from_removed(self):
        context = FilterContext(
            question="q",
            table_scores={"a": 0.3, "b": 0.2, "c": 0.1},
        )
        result = SemanticFilter(threshold=0.5, min_tables=2).filter(["a", "b", "c"], context)
        assert len(result.tables) == 2
        assert result.tables == ["a", "b"]


class TestBridgeFilter:
    def test_adds_bridges_without_mutating_original_tables(self):
        neo4j = FakeNeo4jReader(bridges=["bridge_tbl"])
        context = FilterContext(question="q", original_tables=["a", "b"])

        result = BridgeFilter(neo4j_reader=neo4j).filter(["a", "b"], context)

        assert "bridge_tbl" in result.tables
        # provenance stays pure: original recall list is never rewritten
        assert context.original_tables == ["a", "b"]
        assert "bridge_tbl" in context.must_keep
        assert context.table_provenance["bridge_tbl"] == "bridge"

    def test_direct_neighbor_expansion_is_batched(self):
        neo4j = FakeNeo4jReader(bridges=[], neighbors=["dept"])
        context = FilterContext(question="q", original_tables=["a", "b"])

        BridgeFilter(
            neo4j_reader=neo4j,
            include_direct_neighbors=True,
            protected_tables={"dept"},
        ).filter(["a", "b"], context)

        # One batched expand call for all tables, not one per table
        assert len(neo4j.expand_calls) == 1
        assert neo4j.expand_calls[0]["tables"] == ["a", "b"]

    def test_no_neighbor_query_without_protected_tables(self):
        neo4j = FakeNeo4jReader(bridges=[])
        context = FilterContext(question="q", original_tables=["a", "b"])

        BridgeFilter(neo4j_reader=neo4j, include_direct_neighbors=True).filter(["a", "b"], context)

        assert neo4j.expand_calls == []

    def test_protected_neighbor_added_with_provenance(self):
        neo4j = FakeNeo4jReader(bridges=[], neighbors=["dept", "noise"])
        context = FilterContext(question="q", original_tables=["a", "b"])

        result = BridgeFilter(
            neo4j_reader=neo4j,
            include_direct_neighbors=True,
            protected_tables={"dept"},
        ).filter(["a", "b"], context)

        assert "dept" in result.tables
        assert "noise" not in result.tables
        assert context.table_provenance["dept"] == "direct_neighbor"
        assert context.original_tables == ["a", "b"]

    def test_skips_with_fewer_than_two_tables(self):
        neo4j = FakeNeo4jReader(bridges=["x"])
        context = FilterContext(question="q", original_tables=["a"])
        result = BridgeFilter(neo4j_reader=neo4j).filter(["a"], context)
        assert result.tables == ["a"]
        assert neo4j.find_bridge_calls == []
