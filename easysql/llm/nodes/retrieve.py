from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from easysql.config import get_settings
from easysql.embeddings.embedding_service import EmbeddingService
from easysql.llm.nodes.base import BaseNode
from easysql.llm.state import EasySQLState
from easysql.readers.milvus_reader import MilvusSchemaReader
from easysql.readers.neo4j_reader import Neo4jSchemaReader
from easysql.repositories.milvus_repository import MilvusRepository
from easysql.repositories.neo4j_repository import Neo4jRepository
from easysql.retrieval.schema_retrieval import SchemaRetrievalService
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.types import StreamWriter

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_retrieval_service() -> SchemaRetrievalService:
    settings = get_settings()

    embedding_service = EmbeddingService.from_settings(settings)

    milvus_repo = MilvusRepository(
        uri=settings.milvus_uri,
        token=settings.milvus_token,
        collection_prefix=settings.milvus_collection_prefix,
    )
    milvus_repo.connect()

    neo4j_repo = Neo4jRepository(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )
    neo4j_repo.connect()

    milvus_reader = MilvusSchemaReader(
        repository=milvus_repo,
        embedding_service=embedding_service,
    )

    neo4j_reader = Neo4jSchemaReader(repository=neo4j_repo)

    return SchemaRetrievalService.from_settings(
        milvus_reader=milvus_reader,
        neo4j_reader=neo4j_reader,
        settings=settings,
    )


class RetrieveNode(BaseNode):
    def __init__(self, service: SchemaRetrievalService | None = None):
        self._service = service

    @property
    def service(self) -> SchemaRetrievalService:
        if self._service is None:
            self._service = get_retrieval_service()
        return self._service

    def __call__(
        self,
        state: EasySQLState,
        config: "RunnableConfig | None" = None,
        *,
        writer: "StreamWriter | None" = None,
    ) -> dict[Any, Any]:
        clarified_query = state.get("clarified_query")
        query = clarified_query or state["raw_query"]

        initial_tables = None
        schema_hint = state.get("schema_hint")
        if schema_hint and not clarified_query:
            initial_tables = [
                {
                    "name": t["name"],
                    "score": t["score"],
                    "chinese_name": t.get("chinese_name"),
                    "description": t.get("description"),
                }
                for t in schema_hint["tables"]
            ]

        result = self.service.retrieve(
            question=query,
            db_name=state.get("db_name"),
            initial_tables=initial_tables,
        )

        return {"retrieval_result": result.__dict__}


def retrieve_node(
    state: EasySQLState,
    config: "RunnableConfig | None" = None,
    *,
    writer: "StreamWriter | None" = None,
) -> dict[Any, Any]:
    node = RetrieveNode()
    return node(state, config, writer=writer)


def _close_reader_repositories(service: SchemaRetrievalService) -> None:
    milvus_reader = getattr(service, "_milvus", None)
    neo4j_reader = getattr(service, "_neo4j", None)

    milvus_repo = getattr(milvus_reader, "_repo", None)
    if milvus_repo is not None and hasattr(milvus_repo, "close"):
        milvus_repo.close()

    neo4j_repo = getattr(neo4j_reader, "_repo", None)
    if neo4j_repo is not None and hasattr(neo4j_repo, "close"):
        neo4j_repo.close()


def reset_retrieval_service_cache() -> None:
    cache_info_fn = getattr(get_retrieval_service, "cache_info", None)
    should_close = False
    if callable(cache_info_fn):
        should_close = getattr(cache_info_fn(), "currsize", 0) > 0

    if should_close:
        service = get_retrieval_service()
        _close_reader_repositories(service)

    get_retrieval_service.cache_clear()


def warm_retrieval_service_cache() -> None:
    get_retrieval_service()
