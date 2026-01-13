"""Simplified Milvus writer for code chunks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pymilvus import DataType

from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from pymilvus import MilvusClient

    from easysql.code_context.chunker import CodeChunk
    from easysql.embeddings.embedding_service import EmbeddingService

logger = get_logger(__name__)


@dataclass
class CodeMilvusConfig:
    collection_name: str = "code_chunks"
    database_prefix: str = ""

    def get_collection_name(self) -> str:
        if self.database_prefix:
            return f"{self.database_prefix}_{self.collection_name}"
        return self.collection_name


class CodeMilvusWriter:
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

    def create_collection(self, drop_existing: bool = False) -> None:
        collection_name = self.collection_name
        dim = self._embedding.dimension

        if self._client.has_collection(collection_name):
            if drop_existing:
                logger.warning(f"Dropping existing collection: {collection_name}")
                self._client.drop_collection(collection_name)
            else:
                logger.info(f"Collection already exists: {collection_name}")
                return

        logger.info(f"Creating collection: {collection_name} (dim={dim})")

        schema = self._client.create_schema(auto_id=False, enable_dynamic_field=False)

        schema.add_field("id", DataType.VARCHAR, max_length=512, is_primary=True)
        schema.add_field("file_path", DataType.VARCHAR, max_length=512)
        schema.add_field("file_hash", DataType.VARCHAR, max_length=64)
        schema.add_field("language", DataType.VARCHAR, max_length=32)
        schema.add_field("content", DataType.VARCHAR, max_length=16000)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dim)

        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 16, "efConstruction": 256},
        )

        self._client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,
        )
        logger.info(f"Collection created: {collection_name}")

    def upsert_chunks(
        self,
        chunks: list["CodeChunk"],
        batch_size: int = 100,
    ) -> int:
        if not chunks:
            return 0

        texts = [chunk.to_embedding_text() for chunk in chunks]
        embeddings = self._embedding.encode_batch(texts, batch_size=batch_size)

        data = []
        for chunk, embedding in zip(chunks, embeddings):
            data.append(
                {
                    "id": chunk.chunk_id,
                    "file_path": chunk.file_path,
                    "file_hash": chunk.file_hash,
                    "language": chunk.language,
                    "content": chunk.content[:16000],
                    "embedding": embedding,
                }
            )

        total = 0
        for i in range(0, len(data), batch_size):
            batch = data[i : i + batch_size]
            self._client.upsert(collection_name=self.collection_name, data=batch)
            total += len(batch)

        logger.info(f"Upserted {total} chunks to {self.collection_name}")
        return total

    def delete_by_file_paths(self, file_paths: set[str]) -> int:
        if not file_paths:
            return 0

        if not self._client.has_collection(self.collection_name):
            return 0

        paths_str = ", ".join(f'"{p}"' for p in file_paths)
        filter_expr = f"file_path in [{paths_str}]"

        try:
            result = self._client.delete(
                collection_name=self.collection_name,
                filter=filter_expr,
            )
            deleted = result.get("delete_count", 0) if isinstance(result, dict) else 0
            logger.info(f"Deleted {deleted} chunks for {len(file_paths)} files")
            return deleted
        except Exception as e:
            logger.warning(f"Failed to delete chunks: {e}")
            return 0

    def delete_by_file_prefix(self, prefix: str) -> int:
        if not self._client.has_collection(self.collection_name):
            return 0

        filter_expr = f'file_path like "{prefix}%"'

        try:
            result = self._client.delete(
                collection_name=self.collection_name,
                filter=filter_expr,
            )
            deleted = result.get("delete_count", 0) if isinstance(result, dict) else 0
            logger.info(f"Deleted {deleted} chunks with prefix {prefix}")
            return deleted
        except Exception as e:
            logger.warning(f"Failed to delete chunks by prefix: {e}")
            return 0

    def get_stats(self) -> dict[str, Any]:
        if not self._client.has_collection(self.collection_name):
            return {"collection": self.collection_name, "exists": False}

        info = self._client.get_collection_stats(self.collection_name)
        return {
            "collection": self.collection_name,
            "row_count": info.get("row_count", 0),
        }
