"""Simplified Milvus reader for code chunks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from pymilvus import MilvusClient

    from easysql.embeddings.embedding_service import EmbeddingService

from .milvus_writer import CodeMilvusConfig

logger = get_logger(__name__)


class CodeMilvusReader:
    def __init__(
        self,
        client: "MilvusClient",
        embedding_service: "EmbeddingService",
        config: CodeMilvusConfig | None = None,
    ):
        self._client = client
        self._embedding = embedding_service
        self._config = config or CodeMilvusConfig()

    @property
    def collection_name(self) -> str:
        return self._config.get_collection_name()

    def search(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.0,
        filter_expr: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self._client.has_collection(self.collection_name):
            logger.warning(f"Collection not found: {self.collection_name}")
            return []

        query_embedding = self._embedding.encode(query)

        search_params = {"metric_type": "COSINE", "params": {"ef": 64}}

        results = self._client.search(
            collection_name=self.collection_name,
            data=[query_embedding],
            limit=top_k,
            search_params=search_params,
            filter=filter_expr,
            output_fields=["file_path", "language", "content"],
        )

        chunks = []
        for hit in results[0]:
            score = hit["distance"]
            if score < score_threshold:
                continue

            entity = hit["entity"]
            chunks.append(
                {
                    "file_path": entity.get("file_path", ""),
                    "language": entity.get("language", ""),
                    "content": entity.get("content", ""),
                    "score": score,
                }
            )

        return chunks

    def search_with_tables(
        self,
        query: str,
        table_names: list[str] | None = None,
        top_k: int = 5,
        score_threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        enhanced_query = query
        if table_names:
            enhanced_query = f"{query} {' '.join(table_names)}"

        return self.search(
            query=enhanced_query,
            top_k=top_k,
            score_threshold=score_threshold,
        )
