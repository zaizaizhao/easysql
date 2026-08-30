"""
Milvus Schema Reader - Semantic search for schema retrieval.
"""

import re

from easysql.embeddings.embedding_service import EmbeddingService
from easysql.repositories.milvus_repository import MilvusRepository
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


def _sanitize_filter_value(value: str) -> str:
    """Sanitize a string value for use in Milvus filter expressions."""
    if not value:
        return ""
    if not re.match(r"^[\w\-_.]+$", value):
        value = value.replace("\\", "\\\\").replace('"', '\\"')
    return value


def _build_filter_expr(
    db_name: str | None = None,
    table_filter: list[str] | None = None,
    extra_expr: str | None = None,
) -> str | None:
    """Combine db isolation, table restriction, and extra expressions with AND."""
    parts: list[str] = []

    if db_name:
        parts.append(f'database_name == "{_sanitize_filter_value(db_name)}"')

    if table_filter:
        tables_str = ", ".join(f'"{_sanitize_filter_value(t)}"' for t in table_filter)
        parts.append(f"table_name in [{tables_str}]")

    if extra_expr:
        parts.append(f"({extra_expr})")

    if not parts:
        return None
    return " and ".join(parts)


class MilvusSchemaReader:
    """Read-only Milvus queries for semantic schema search.

    ``db_name`` is a first-class parameter on all search methods: when provided,
    the reader itself enforces database isolation instead of leaving it to
    callers via hand-built filter expressions.
    """

    def __init__(self, repository: MilvusRepository, embedding_service: EmbeddingService):
        self._repo = repository
        self._embedding_service = embedding_service

    @property
    def client(self):
        return self._repo.client

    @property
    def table_collection(self) -> str:
        return self._repo.table_collection

    @property
    def column_collection(self) -> str:
        return self._repo.column_collection

    def search_tables(
        self,
        query: str,
        top_k: int = 10,
        db_name: str | None = None,
        table_filter: list[str] | None = None,
        filter_expr: str | None = None,
    ) -> list[dict]:
        """Search for similar tables by query text.

        Args:
            query: Natural language query for semantic search.
            top_k: Maximum number of results.
            db_name: Restrict results to this logical database.
            table_filter: Restrict results to these table names (single batched
                call — use instead of per-table lookups).
            filter_expr: Extra raw filter expression, AND-combined with the above.
        """
        query_embedding = self._embedding_service.encode(query)

        search_params = {"metric_type": "COSINE", "params": {"ef": 64}}

        results = self.client.search(
            collection_name=self.table_collection,
            data=[query_embedding],
            limit=top_k,
            search_params=search_params,
            filter=_build_filter_expr(db_name, table_filter, filter_expr),
            output_fields=[
                "database_name",
                "schema_name",
                "table_name",
                "chinese_name",
                "description",
                "business_domain",
            ],
        )

        return [
            {
                "table_name": hit["entity"]["table_name"],
                "database_name": hit["entity"]["database_name"],
                "schema_name": hit["entity"].get("schema_name") or "public",
                "chinese_name": hit["entity"]["chinese_name"],
                "description": hit["entity"]["description"],
                "score": hit["distance"],
            }
            for hit in results[0]
        ]

    def search_columns(
        self,
        query: str,
        top_k: int = 20,
        db_name: str | None = None,
        table_filter: list[str] | None = None,
    ) -> list[dict]:
        """Search for similar columns by query text.

        Args:
            query: Natural language query for semantic search.
            top_k: Maximum number of results.
            db_name: Restrict results to this logical database.
            table_filter: Restrict results to columns of these tables.
        """
        query_embedding = self._embedding_service.encode(query)

        search_params = {"metric_type": "COSINE", "params": {"ef": 64}}

        common_kwargs = {
            "collection_name": self.column_collection,
            "data": [query_embedding],
            "limit": top_k,
            "search_params": search_params,
            "filter": _build_filter_expr(db_name, table_filter),
        }
        output_fields = [
            "database_name",
            "schema_name",
            "qualified_table_id",
            "table_name",
            "column_name",
            "chinese_name",
            "data_type",
            "is_pk",
            "is_fk",
        ]
        try:
            results = self.client.search(**common_kwargs, output_fields=output_fields)
        except Exception as exc:  # noqa: BLE001 - one-release legacy collection compatibility
            logger.warning(
                "Column collection does not expose multi-database metadata yet; "
                "retrying with legacy fields. Run schema sync to rebuild it. Error: {}",
                exc,
            )
            results = self.client.search(
                **common_kwargs,
                output_fields=[
                    "database_name",
                    "table_name",
                    "column_name",
                    "chinese_name",
                    "data_type",
                    "is_pk",
                    "is_fk",
                ],
            )

        return [
            {
                "database_name": hit["entity"]["database_name"],
                "schema_name": hit["entity"].get("schema_name") or "public",
                "qualified_table_id": hit["entity"].get("qualified_table_id"),
                "table_name": hit["entity"]["table_name"],
                "column_name": hit["entity"]["column_name"],
                "chinese_name": hit["entity"]["chinese_name"],
                "data_type": hit["entity"]["data_type"],
                "is_pk": hit["entity"]["is_pk"],
                "is_fk": hit["entity"]["is_fk"],
                "score": hit["distance"],
            }
            for hit in results[0]
        ]

    def get_collection_stats(self) -> dict:
        """Get statistics for all collections."""
        stats = {}

        for collection_name in [self.table_collection, self.column_collection]:
            if self.client.has_collection(collection_name):
                info = self.client.get_collection_stats(collection_name)
                stats[collection_name] = {
                    "row_count": info.get("row_count", 0),
                }
            else:
                stats[collection_name] = {"exists": False}

        return stats
