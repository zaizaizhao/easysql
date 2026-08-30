"""Runtime adapters for the standalone read-only agent tool module."""

from __future__ import annotations

import atexit
import inspect
import json
from importlib import import_module
from threading import RLock
from typing import TYPE_CHECKING, Any

from easysql.agent_tools.service import SchemaToolService
from easysql.embeddings.embedding_service import EmbeddingService
from easysql.readers.neo4j_reader import Neo4jSchemaReader
from easysql.repositories.milvus_repository import MilvusRepository
from easysql.repositories.neo4j_repository import Neo4jRepository
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from easysql.config import Settings

logger = get_logger(__name__)


def _build_filter(db_name: str, table_filter: list[str] | None) -> str:
    parts = [f"database_name == {json.dumps(db_name, ensure_ascii=False)}"]
    if table_filter:
        tables = ", ".join(json.dumps(name, ensure_ascii=False) for name in table_filter)
        parts.append(f"table_name in [{tables}]")
    return " and ".join(parts)


class MilvusAgentSearchAdapter:
    """Database-scoped Milvus adapter used when no shared retrieval runtime exists."""

    def __init__(
        self,
        *,
        repository: MilvusRepository,
        embedding_service: EmbeddingService,
    ) -> None:
        self._repository = repository
        self._embedding_service = embedding_service

    def search_tables(
        self,
        query: str,
        top_k: int = 10,
        db_name: str | None = None,
        table_filter: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not db_name:
            raise ValueError("db_name is required")
        common = {
            "collection_name": self._repository.table_collection,
            "data": [self._embedding_service.encode(query)],
            "limit": top_k,
            "search_params": {"metric_type": "COSINE", "params": {"ef": 64}},
            "filter": _build_filter(db_name, table_filter),
        }
        try:
            results = self._repository.client.search(
                **common,
                output_fields=[
                    "database_name",
                    "schema_name",
                    "table_name",
                    "chinese_name",
                    "description",
                    "business_domain",
                ],
            )
        except Exception:  # noqa: BLE001 - supports one-release legacy collections
            logger.warning("Retrying table search with legacy Milvus output fields")
            results = self._repository.client.search(
                **common,
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
                "database_name": hit["entity"].get("database_name"),
                "schema_name": hit["entity"].get("schema_name"),
                "table_name": hit["entity"].get("table_name"),
                "chinese_name": hit["entity"].get("chinese_name"),
                "description": hit["entity"].get("description"),
                "business_domain": hit["entity"].get("business_domain"),
                "score": hit.get("distance", 0.0),
            }
            for hit in results[0]
        ]

    def search_columns(
        self,
        query: str,
        top_k: int = 20,
        db_name: str | None = None,
        table_filter: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not db_name:
            raise ValueError("db_name is required")
        common = {
            "collection_name": self._repository.column_collection,
            "data": [self._embedding_service.encode(query)],
            "limit": top_k,
            "search_params": {"metric_type": "COSINE", "params": {"ef": 64}},
            "filter": _build_filter(db_name, table_filter),
        }
        try:
            results = self._repository.client.search(
                **common,
                output_fields=[
                    "database_name",
                    "schema_name",
                    "qualified_table_id",
                    "table_name",
                    "column_name",
                    "chinese_name",
                    "data_type",
                    "is_pk",
                    "is_fk",
                ],
            )
        except Exception:  # noqa: BLE001 - supports one-release legacy collections
            logger.warning("Retrying column search with legacy Milvus output fields")
            results = self._repository.client.search(
                **common,
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
                "database_name": hit["entity"].get("database_name"),
                "schema_name": hit["entity"].get("schema_name"),
                "qualified_table_id": hit["entity"].get("qualified_table_id"),
                "table_name": hit["entity"].get("table_name"),
                "column_name": hit["entity"].get("column_name"),
                "chinese_name": hit["entity"].get("chinese_name"),
                "data_type": hit["entity"].get("data_type"),
                "is_pk": hit["entity"].get("is_pk", False),
                "is_fk": hit["entity"].get("is_fk", False),
                "score": hit.get("distance", 0.0),
            }
            for hit in results[0]
        ]


class _StandaloneAgentToolRuntime:
    """Own resources only when the application has no shared retrieval runtime."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.embedding_service = EmbeddingService.from_settings(settings)
        self.milvus_repository = MilvusRepository(
            uri=settings.milvus_uri,
            token=settings.milvus_token,
            collection_prefix=getattr(settings, "milvus_collection_prefix", ""),
        )

        neo4j_kwargs: dict[str, Any] = {
            "uri": settings.neo4j_uri,
            "user": settings.neo4j_user,
            "password": settings.neo4j_password,
            "database": settings.neo4j_database,
        }
        if "project_namespace" in inspect.signature(Neo4jRepository).parameters:
            neo4j_kwargs["project_namespace"] = getattr(settings, "project_namespace", "default")
        self.neo4j_repository = Neo4jRepository(**neo4j_kwargs)

        self.milvus_reader = MilvusAgentSearchAdapter(
            repository=self.milvus_repository,
            embedding_service=self.embedding_service,
        )
        self.neo4j_reader = Neo4jSchemaReader(repository=self.neo4j_repository)

    def close(self) -> None:
        clear_cache = getattr(self.embedding_service, "clear_query_cache", None)
        if callable(clear_cache):
            clear_cache()
        self.milvus_repository.close()
        self.neo4j_repository.close()


_standalone_lock = RLock()
_standalone_runtime: _StandaloneAgentToolRuntime | None = None


def _get_standalone_runtime(settings: Settings) -> _StandaloneAgentToolRuntime:
    global _standalone_runtime
    with _standalone_lock:
        if _standalone_runtime is not None and _standalone_runtime.settings is not settings:
            _standalone_runtime.close()
            _standalone_runtime = None
        if _standalone_runtime is None:
            _standalone_runtime = _StandaloneAgentToolRuntime(settings)
        return _standalone_runtime


def reset_standalone_agent_tool_runtime() -> None:
    """Close the fallback runtime; mainly useful for settings reloads and tests."""
    global _standalone_runtime
    with _standalone_lock:
        if _standalone_runtime is not None:
            _standalone_runtime.close()
            _standalone_runtime = None


def _get_shared_retrieval_runtime() -> Any | None:
    """Use the main process runtime when that optional module is available."""
    try:
        module = import_module("easysql.retrieval.runtime")
    except ModuleNotFoundError as exc:
        if exc.name != "easysql.retrieval.runtime":
            raise
        return None
    getter = getattr(module, "get_retrieval_runtime", None)
    return getter() if callable(getter) else None


def get_schema_tool_service() -> SchemaToolService:
    """FastAPI dependency that keeps agent tools separate from workflow assembly."""
    from easysql.config import get_settings

    settings = get_settings()
    runtime = _get_shared_retrieval_runtime() or _get_standalone_runtime(settings)
    return SchemaToolService(
        settings=settings,
        milvus=runtime.milvus_reader,
        neo4j=runtime.neo4j_reader,
    )


atexit.register(reset_standalone_agent_tool_runtime)
