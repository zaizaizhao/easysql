"""Shared runtime resources for online retrieval.

The SQL-generation graph has several retrieval nodes, but they all use the
same embedding model and the same Milvus/Neo4j backends.  This module owns
those heavyweight resources behind one lifecycle interface so callers do not
create duplicate models, clients, or drivers.
"""

from __future__ import annotations

from functools import lru_cache
from threading import RLock
from typing import TYPE_CHECKING

from easysql.embeddings.embedding_service import EmbeddingService
from easysql.readers.few_shot_reader import FewShotReader
from easysql.readers.milvus_reader import MilvusSchemaReader
from easysql.readers.neo4j_reader import Neo4jSchemaReader
from easysql.repositories.milvus_repository import MilvusRepository
from easysql.repositories.neo4j_repository import Neo4jRepository
from easysql.utils.logger import get_logger

from .schema_retrieval import SchemaRetrievalService

if TYPE_CHECKING:
    from easysql.code_context.retrieval.code_retrieval import CodeRetrievalService
    from easysql.config import Settings

logger = get_logger(__name__)


class RetrievalRuntime:
    """Own shared online-retrieval resources for one application process."""

    def __init__(
        self,
        *,
        settings: Settings,
        embedding_service: EmbeddingService,
        milvus_repository: MilvusRepository,
        neo4j_repository: Neo4jRepository,
    ) -> None:
        self._settings = settings
        self._embedding_service = embedding_service
        self._milvus_repository = milvus_repository
        self._neo4j_repository = neo4j_repository
        self._lock = RLock()
        self._closed = False

        self._milvus_reader = MilvusSchemaReader(
            repository=milvus_repository,
            embedding_service=embedding_service,
        )
        self._neo4j_reader = Neo4jSchemaReader(repository=neo4j_repository)
        self._schema_retrieval = SchemaRetrievalService.from_settings(
            milvus_reader=self._milvus_reader,
            neo4j_reader=self._neo4j_reader,
            settings=settings,
        )

        self._few_shot_reader: FewShotReader | None = None
        self._code_retrieval: CodeRetrievalService | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> RetrievalRuntime:
        """Create and connect one runtime from application settings."""
        embedding_service = EmbeddingService.from_settings(settings)
        milvus_repository = MilvusRepository(
            uri=settings.milvus_uri,
            token=settings.milvus_token,
            collection_prefix=settings.project_namespace,
        )
        neo4j_repository = Neo4jRepository(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
            project_namespace=settings.project_namespace,
        )

        try:
            milvus_repository.connect()
            neo4j_repository.connect()
            return cls(
                settings=settings,
                embedding_service=embedding_service,
                milvus_repository=milvus_repository,
                neo4j_repository=neo4j_repository,
            )
        except Exception:
            milvus_repository.close()
            neo4j_repository.close()
            raise

    @property
    def embedding_service(self) -> EmbeddingService:
        self._ensure_open()
        return self._embedding_service

    @property
    def milvus_repository(self) -> MilvusRepository:
        self._ensure_open()
        return self._milvus_repository

    @property
    def milvus_reader(self) -> MilvusSchemaReader:
        self._ensure_open()
        return self._milvus_reader

    @property
    def neo4j_reader(self) -> Neo4jSchemaReader:
        self._ensure_open()
        return self._neo4j_reader

    @property
    def schema_retrieval(self) -> SchemaRetrievalService:
        self._ensure_open()
        return self._schema_retrieval

    @property
    def few_shot_reader(self) -> FewShotReader:
        with self._lock:
            self._ensure_open()
            if self._few_shot_reader is None:
                self._few_shot_reader = FewShotReader(
                    repository=self._milvus_repository,
                    embedding_service=self._embedding_service,
                )
            return self._few_shot_reader

    @property
    def code_retrieval(self) -> CodeRetrievalService | None:
        self._ensure_open()
        if not self._settings.code_context_enabled:
            return None

        with self._lock:
            self._ensure_open()
            if self._code_retrieval is None:
                from easysql.code_context.factory import CodeContextFactory

                self._code_retrieval = CodeContextFactory.create_retrieval_service(
                    client=self._milvus_repository.client,
                    embedding_service=self._embedding_service,
                    settings=self._settings,
                )
            return self._code_retrieval

    def close(self) -> None:
        """Close shared clients once and make this runtime unusable."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._embedding_service.clear_query_cache()
            try:
                self._milvus_repository.close()
            finally:
                self._neo4j_repository.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("RetrievalRuntime is closed")


_runtime_lock = RLock()


@lru_cache(maxsize=1)
def _get_cached_runtime() -> RetrievalRuntime:
    from easysql.config import get_settings

    return RetrievalRuntime.from_settings(get_settings())


def get_retrieval_runtime() -> RetrievalRuntime:
    """Return the process-wide retrieval runtime."""
    with _runtime_lock:
        return _get_cached_runtime()


def reset_retrieval_runtime() -> None:
    """Close and clear the process-wide retrieval runtime, if initialized."""
    with _runtime_lock:
        if _get_cached_runtime.cache_info().currsize:
            _get_cached_runtime().close()
        _get_cached_runtime.cache_clear()


def warm_retrieval_runtime() -> None:
    """Initialize shared clients without forcing the embedding model to load."""
    get_retrieval_runtime()
