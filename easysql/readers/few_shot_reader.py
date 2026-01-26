"""Few-Shot Milvus reader for semantic retrieval of Q&A examples."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from easysql.embeddings.embedding_service import EmbeddingService
from easysql.repositories.milvus_repository import MilvusRepository
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


def _sanitize_filter_value(value: str) -> str:
    """Sanitize a string value for use in Milvus filter expressions.

    Escapes special characters and validates input to prevent injection.

    Args:
        value: The raw string value to sanitize.

    Returns:
        Sanitized string safe for use in filter expressions.

    Raises:
        ValueError: If the value contains invalid characters.
    """
    if not value:
        return ""
    # Only allow alphanumeric, underscore, hyphen, and common safe characters
    if not re.match(r"^[\w\-_.]+$", value):
        # If contains special chars, escape double quotes and backslashes
        value = value.replace("\\", "\\\\").replace('"', '\\"')
    return value


@dataclass
class FewShotResult:
    """A retrieved few-shot example."""

    id: str
    db_name: str
    question: str
    sql: str
    tables_used: list[str]
    explanation: str
    message_id: str
    created_at: datetime
    score: float


class FewShotReader:
    """Reads few-shot examples from Milvus with semantic search."""

    COLLECTION_NAME = "few_shot_examples"

    # Common output fields for all queries
    OUTPUT_FIELDS = [
        "id",
        "db_name",
        "question",
        "sql",
        "tables_used",
        "explanation",
        "message_id",
        "created_at",
    ]

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

    def _parse_entity(self, entity: dict, score: float = 1.0) -> FewShotResult:
        """Parse a Milvus entity into a FewShotResult.

        Args:
            entity: Raw entity dict from Milvus.
            score: Similarity score (default 1.0 for non-search queries).

        Returns:
            Parsed FewShotResult object.
        """
        tables_str = entity.get("tables_used", "")
        tables = [t.strip() for t in tables_str.split(",") if t.strip()]

        created_ts = entity.get("created_at", 0)
        created_at = datetime.fromtimestamp(created_ts, tz=timezone.utc)

        return FewShotResult(
            id=entity["id"],
            db_name=entity["db_name"],
            question=entity["question"],
            sql=entity["sql"],
            tables_used=tables,
            explanation=entity.get("explanation", ""),
            message_id=entity.get("message_id", ""),
            created_at=created_at,
            score=score,
        )

    def search_similar(
        self,
        query: str,
        db_name: str,
        top_k: int = 3,
        min_score: float = 0.6,
    ) -> list[FewShotResult]:
        """Search for semantically similar few-shot examples.

        Args:
            query: The natural language query to search for.
            db_name: Database name to filter by.
            top_k: Maximum number of results to return.
            min_score: Minimum similarity score threshold.

        Returns:
            List of FewShotResult ordered by similarity score.
        """
        if not self.client.has_collection(self.collection_name):
            logger.warning(f"Collection {self.collection_name} does not exist")
            return []

        safe_db_name = _sanitize_filter_value(db_name)
        query_embedding = self._embedding_service.encode(query)
        search_params = {"metric_type": "COSINE", "params": {"ef": 64}}

        results = self.client.search(
            collection_name=self.collection_name,
            data=[query_embedding],
            limit=top_k,
            search_params=search_params,
            filter=f'db_name == "{safe_db_name}"',
            output_fields=self.OUTPUT_FIELDS,
        )

        examples = []
        for hit in results[0]:
            score = hit["distance"]
            if score < min_score:
                continue
            examples.append(self._parse_entity(hit["entity"], score=score))

        return examples

    def list_by_db(
        self,
        db_name: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FewShotResult]:
        """List all few-shot examples for a database.

        Args:
            db_name: Database name to filter by.
            limit: Maximum number of results.
            offset: Offset for pagination.

        Returns:
            List of FewShotResult ordered by creation time (newest first).
        """
        if not self.client.has_collection(self.collection_name):
            return []

        safe_db_name = _sanitize_filter_value(db_name)
        results = self.client.query(
            collection_name=self.collection_name,
            filter=f'db_name == "{safe_db_name}"',
            output_fields=self.OUTPUT_FIELDS,
            limit=limit,
            offset=offset,
        )

        examples = [self._parse_entity(entity) for entity in results]
        return sorted(examples, key=lambda x: x.created_at, reverse=True)

    def get_by_id(self, example_id: str) -> FewShotResult | None:
        """Get a specific few-shot example by ID.

        Args:
            example_id: The unique identifier of the example.

        Returns:
            FewShotResult if found, None otherwise.
        """
        if not self.client.has_collection(self.collection_name):
            return None

        safe_id = _sanitize_filter_value(example_id)
        results = self.client.query(
            collection_name=self.collection_name,
            filter=f'id == "{safe_id}"',
            output_fields=self.OUTPUT_FIELDS,
            limit=1,
        )

        if not results:
            return None

        return self._parse_entity(results[0])

    def get_by_message_id(self, message_id: str) -> FewShotResult | None:
        """Get a few-shot example by its associated message ID.

        Args:
            message_id: The message ID to search for.

        Returns:
            FewShotResult if found, None otherwise.
        """
        if not self.client.has_collection(self.collection_name):
            return None

        if not message_id:
            return None

        safe_message_id = _sanitize_filter_value(message_id)
        results = self.client.query(
            collection_name=self.collection_name,
            filter=f'message_id == "{safe_message_id}"',
            output_fields=self.OUTPUT_FIELDS,
            limit=1,
        )

        if not results:
            return None

        return self._parse_entity(results[0])

    def count_by_db(self, db_name: str) -> int:
        """Count the number of few-shot examples for a database.

        Args:
            db_name: Database name to filter by.

        Returns:
            Number of examples in the database.
        """
        if not self.client.has_collection(self.collection_name):
            return 0

        safe_db_name = _sanitize_filter_value(db_name)
        results = self.client.query(
            collection_name=self.collection_name,
            filter=f'db_name == "{safe_db_name}"',
            output_fields=["id"],
        )
        return len(results)

    def check_duplicate(
        self,
        question: str,
        db_name: str,
        threshold: float = 0.95,
    ) -> FewShotResult | None:
        """Check if a similar question already exists.

        Args:
            question: The question to check for duplicates.
            db_name: Database name to search within.
            threshold: Similarity threshold for duplicate detection.

        Returns:
            Existing FewShotResult if duplicate found, None otherwise.
        """
        results = self.search_similar(
            query=question,
            db_name=db_name,
            top_k=1,
            min_score=threshold,
        )
        return results[0] if results else None
