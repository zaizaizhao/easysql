"""Few-Shot Milvus writer for storing Q&A examples."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from pymilvus import DataType

from easysql.embeddings.embedding_service import EmbeddingService
from easysql.repositories.milvus_repository import MilvusRepository
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


def _sanitize_filter_value(value: str) -> str:
    """Sanitize a string value for use in Milvus filter expressions.

    Args:
        value: The raw string value to sanitize.

    Returns:
        Sanitized string safe for use in filter expressions.
    """
    if not value:
        return ""
    if not re.match(r"^[\w\-_.]+$", value):
        value = value.replace("\\", "\\\\").replace('"', '\\"')
    return value


class DuplicateExampleError(Exception):
    """Raised when attempting to insert a duplicate few-shot example."""

    def __init__(self, existing_id: str, similarity_score: float):
        self.existing_id = existing_id
        self.similarity_score = similarity_score
        super().__init__(
            f"Similar example already exists (id={existing_id}, score={similarity_score:.2f})"
        )


class FewShotWriter:
    """Writes few-shot examples to Milvus for semantic retrieval."""

    COLLECTION_NAME = "few_shot_examples"
    DUPLICATE_THRESHOLD = 0.95  # Similarity threshold for duplicate detection

    def __init__(
        self,
        repository: MilvusRepository,
        embedding_service: EmbeddingService,
        collection_name: str | None = None,
    ):
        self._repo = repository
        self._embedding_service = embedding_service
        self._collection_name = collection_name or self.COLLECTION_NAME

    @property
    def client(self):
        return self._repo.client

    @property
    def collection_name(self) -> str:
        if self._repo.collection_prefix:
            return f"{self._repo.collection_prefix}_{self._collection_name}"
        return self._collection_name

    def create_collection(self, drop_existing: bool = False) -> None:
        """Create the few-shot examples collection in Milvus.

        Args:
            drop_existing: If True, drop existing collection before creating.
        """
        collection_name = self.collection_name
        dim = self._embedding_service.dimension

        if self.client.has_collection(collection_name):
            if drop_existing:
                logger.warning(f"Dropping existing collection: {collection_name}")
                self.client.drop_collection(collection_name)
            else:
                logger.info(f"Collection already exists: {collection_name}")
                return

        logger.info(f"Creating few-shot collection: {collection_name} (dim={dim})")

        schema = self.client.create_schema(auto_id=False, enable_dynamic_field=False)

        schema.add_field("id", DataType.VARCHAR, max_length=64, is_primary=True)
        schema.add_field("db_name", DataType.VARCHAR, max_length=128)
        schema.add_field("question", DataType.VARCHAR, max_length=2048)
        schema.add_field("sql", DataType.VARCHAR, max_length=8192)
        schema.add_field("tables_used", DataType.VARCHAR, max_length=1024)
        schema.add_field("explanation", DataType.VARCHAR, max_length=2048)
        schema.add_field("message_id", DataType.VARCHAR, max_length=64)
        schema.add_field("created_at", DataType.INT64)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dim)

        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 16, "efConstruction": 256},
        )

        self.client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,
        )
        logger.info(f"Few-shot collection created: {collection_name}")

    def _check_duplicate(
        self,
        question: str,
        db_name: str,
    ) -> tuple[str, float] | None:
        """Check if a similar question already exists.

        Args:
            question: The question to check.
            db_name: Database name to search within.

        Returns:
            Tuple of (existing_id, score) if duplicate found, None otherwise.
        """
        if not self.client.has_collection(self.collection_name):
            return None

        query_embedding = self._embedding_service.encode(question)
        search_params = {"metric_type": "COSINE", "params": {"ef": 64}}
        safe_db_name = _sanitize_filter_value(db_name)

        results = self.client.search(
            collection_name=self.collection_name,
            data=[query_embedding],
            limit=1,
            search_params=search_params,
            filter=f'db_name == "{safe_db_name}"',
            output_fields=["id"],
        )

        if results and results[0]:
            hit = results[0][0]
            score = hit["distance"]
            if score >= self.DUPLICATE_THRESHOLD:
                return (hit["entity"]["id"], score)

        return None

    def insert(
        self,
        db_name: str,
        question: str,
        sql: str,
        tables_used: list[str] | None = None,
        explanation: str | None = None,
        message_id: str | None = None,
        check_duplicate: bool = True,
    ) -> str:
        """Insert a new few-shot example.

        Args:
            db_name: Database name for isolation.
            question: Natural language question.
            sql: SQL query.
            tables_used: List of tables used in the query.
            explanation: Optional explanation of the SQL.
            message_id: Optional related message ID.
            check_duplicate: If True, check for existing similar examples.

        Returns:
            The ID of the inserted example.

        Raises:
            DuplicateExampleError: If a similar example already exists.
        """
        # Check for duplicates if enabled
        if check_duplicate:
            duplicate = self._check_duplicate(question, db_name)
            if duplicate:
                existing_id, score = duplicate
                raise DuplicateExampleError(existing_id, score)

        example_id = str(uuid.uuid4())
        embed_text = f"{question}\n{sql}"
        embedding = self._embedding_service.encode(embed_text)

        data = {
            "id": example_id,
            "db_name": db_name,
            "question": question[:2048],
            "sql": sql[:8192],
            "tables_used": ",".join(tables_used or [])[:1024],
            "explanation": (explanation or "")[:2048],
            "message_id": message_id or "",
            "created_at": int(datetime.now(timezone.utc).timestamp()),
            "embedding": embedding,
        }

        self.client.insert(collection_name=self.collection_name, data=[data])
        logger.info(f"Few-shot example inserted: {example_id} for db={db_name}")
        return example_id

    def update(
        self,
        example_id: str,
        question: str | None = None,
        sql: str | None = None,
        tables_used: list[str] | None = None,
        explanation: str | None = None,
    ) -> bool:
        """Update an existing few-shot example.

        Milvus doesn't support in-place updates, so this performs a delete + insert
        while preserving the original ID, db_name, message_id, and created_at.

        Args:
            example_id: ID of the example to update.
            question: New question text (optional).
            sql: New SQL text (optional).
            tables_used: New list of tables used (optional).
            explanation: New explanation (optional).

        Returns:
            True if update succeeded, False otherwise.
        """
        # First, fetch the existing record
        safe_id = _sanitize_filter_value(example_id)
        results = self.client.query(
            collection_name=self.collection_name,
            filter=f'id == "{safe_id}"',
            output_fields=[
                "id",
                "db_name",
                "question",
                "sql",
                "tables_used",
                "explanation",
                "message_id",
                "created_at",
            ],
            limit=1,
        )

        if not results:
            logger.warning(f"Few-shot example not found for update: {example_id}")
            return False

        existing = results[0]

        # Merge updates with existing values
        new_question = question if question is not None else existing["question"]
        new_sql = sql if sql is not None else existing["sql"]
        new_tables = (
            ",".join(tables_used)[:1024]
            if tables_used is not None
            else existing["tables_used"]
        )
        new_explanation = (
            explanation[:2048] if explanation is not None else existing["explanation"]
        )

        # Generate new embedding if question or sql changed
        if question is not None or sql is not None:
            embed_text = f"{new_question}\n{new_sql}"
            new_embedding = self._embedding_service.encode(embed_text)
        else:
            # Need to fetch old embedding - but Milvus query doesn't return vectors
            # So we recalculate even if unchanged
            embed_text = f"{new_question}\n{new_sql}"
            new_embedding = self._embedding_service.encode(embed_text)

        # Delete old record
        self.client.delete(
            collection_name=self.collection_name,
            filter=f'id == "{safe_id}"',
        )

        # Insert updated record with same ID and preserved fields
        data = {
            "id": existing["id"],
            "db_name": existing["db_name"],
            "question": new_question[:2048],
            "sql": new_sql[:8192],
            "tables_used": new_tables,
            "explanation": new_explanation,
            "message_id": existing["message_id"],
            "created_at": existing["created_at"],
            "embedding": new_embedding,
        }

        self.client.insert(collection_name=self.collection_name, data=[data])
        logger.info(f"Few-shot example updated: {example_id}")
        return True

    def delete(self, example_id: str) -> bool:
        """Delete a few-shot example by ID.

        Args:
            example_id: ID of the example to delete.

        Returns:
            True if deletion succeeded, False otherwise.
        """
        try:
            safe_id = _sanitize_filter_value(example_id)
            self.client.delete(
                collection_name=self.collection_name,
                filter=f'id == "{safe_id}"',
            )
            logger.info(f"Few-shot example deleted: {example_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete few-shot example {example_id}: {e}")
            return False

    def delete_by_db(self, db_name: str) -> int:
        """Delete all few-shot examples for a database.

        Args:
            db_name: Database name to delete examples for.

        Returns:
            1 if deletion succeeded, 0 otherwise.
        """
        try:
            safe_db_name = _sanitize_filter_value(db_name)
            self.client.delete(
                collection_name=self.collection_name,
                filter=f'db_name == "{safe_db_name}"',
            )
            logger.info(f"Deleted all few-shot examples for db={db_name}")
            return 1
        except Exception as e:
            logger.error(f"Failed to delete few-shot examples for db={db_name}: {e}")
            return 0
