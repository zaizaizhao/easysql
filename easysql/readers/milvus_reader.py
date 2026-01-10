"""
Milvus Schema Reader - Semantic search for schema retrieval.
"""

from easysql.embeddings.embedding_service import EmbeddingService
from easysql.repositories.milvus_repository import MilvusRepository
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


class MilvusSchemaReader:
    """Read-only Milvus queries for semantic schema search."""

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
        filter_expr: str | None = None,
    ) -> list[dict]:
        """Search for similar tables by query text."""
        query_embedding = self._embedding_service.encode(query)

        search_params = {"metric_type": "COSINE", "params": {"ef": 64}}

        results = self.client.search(
            collection_name=self.table_collection,
            data=[query_embedding],
            limit=top_k,
            search_params=search_params,
            filter=filter_expr,
            output_fields=[
                "database_name",
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
        table_filter: list[str] | None = None,
    ) -> list[dict]:
        """Search for similar columns by query text."""
        query_embedding = self._embedding_service.encode(query)

        search_params = {"metric_type": "COSINE", "params": {"ef": 64}}

        filter_expr = None
        if table_filter:
            tables_str = ", ".join(f'"{t}"' for t in table_filter)
            filter_expr = f"table_name in [{tables_str}]"

        results = self.client.search(
            collection_name=self.column_collection,
            data=[query_embedding],
            limit=top_k,
            search_params=search_params,
            filter=filter_expr,
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
