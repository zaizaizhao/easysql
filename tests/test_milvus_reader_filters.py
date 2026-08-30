"""Offline unit tests for MilvusSchemaReader filter construction.

Asserts db_name isolation is enforced by the reader itself, without a live
Milvus instance.
"""

from easysql.readers.milvus_reader import MilvusSchemaReader, _build_filter_expr


class FakeEmbeddingService:
    def encode(self, text):
        return [0.0, 0.1, 0.2]


class FakeClient:
    def __init__(self):
        self.search_calls = []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return [[]]


class FakeRepo:
    def __init__(self):
        self.client = FakeClient()
        self.table_collection = "ns_table_embeddings"
        self.column_collection = "ns_column_embeddings"


def make_reader():
    repo = FakeRepo()
    reader = MilvusSchemaReader(repository=repo, embedding_service=FakeEmbeddingService())
    return reader, repo.client


class TestBuildFilterExpr:
    def test_empty_returns_none(self):
        assert _build_filter_expr() is None

    def test_db_only(self):
        assert _build_filter_expr(db_name="his") == 'database_name == "his"'

    def test_tables_only(self):
        assert _build_filter_expr(table_filter=["t1", "t2"]) == 'table_name in ["t1", "t2"]'

    def test_db_and_tables_combined_with_and(self):
        expr = _build_filter_expr(db_name="his", table_filter=["t1"])
        assert expr == 'database_name == "his" and table_name in ["t1"]'

    def test_extra_expr_is_parenthesized(self):
        expr = _build_filter_expr(db_name="his", extra_expr="score > 0")
        assert expr == 'database_name == "his" and (score > 0)'

    def test_special_chars_are_escaped(self):
        expr = _build_filter_expr(db_name='hi"s')
        assert '\\"' in expr


class TestSearchTables:
    def test_db_name_becomes_filter(self):
        reader, client = make_reader()
        reader.search_tables(query="q", top_k=5, db_name="his")

        call = client.search_calls[0]
        assert call["collection_name"] == "ns_table_embeddings"
        assert call["filter"] == 'database_name == "his"'
        assert call["limit"] == 5

    def test_table_filter_batched_in_one_call(self):
        reader, client = make_reader()
        reader.search_tables(query="q", top_k=3, db_name="his", table_filter=["a", "b", "c"])

        assert len(client.search_calls) == 1
        assert (
            client.search_calls[0]["filter"]
            == 'database_name == "his" and table_name in ["a", "b", "c"]'
        )

    def test_no_filter_when_nothing_given(self):
        reader, client = make_reader()
        reader.search_tables(query="q")
        assert client.search_calls[0]["filter"] is None


class TestSearchColumns:
    def test_db_and_table_filter(self):
        reader, client = make_reader()
        reader.search_columns(query="q", top_k=10, db_name="his", table_filter=["t1"])

        call = client.search_calls[0]
        assert call["collection_name"] == "ns_column_embeddings"
        assert call["filter"] == 'database_name == "his" and table_name in ["t1"]'
