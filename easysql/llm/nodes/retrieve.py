"""
Retrieve Schema Node.

Wraps the existing SchemaRetrievalService.
"""

from functools import lru_cache

from easysql.config import get_settings
from easysql.embeddings.embedding_service import EmbeddingService
from easysql.llm.nodes.base import BaseNode
from easysql.llm.state import EasySQLState
from easysql.readers.milvus_reader import MilvusSchemaReader
from easysql.readers.neo4j_reader import Neo4jSchemaReader
from easysql.repositories.milvus_repository import MilvusRepository
from easysql.repositories.neo4j_repository import Neo4jRepository
from easysql.retrieval.schema_retrieval import SchemaRetrievalService


@lru_cache(maxsize=1)
def get_retrieval_service() -> SchemaRetrievalService:
    """Get singleton SchemaRetrievalService instance."""
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
    """Node to retrieve schema based on query."""

    def __init__(self, service: SchemaRetrievalService | None = None):
        self._service = service

    @property
    def service(self) -> SchemaRetrievalService:
        if self._service is None:
            self._service = get_retrieval_service()
        return self._service

    def __call__(self, state: EasySQLState) -> dict:
        query = state["clarified_query"] or state["raw_query"]

        result = self.service.retrieve(question=query, db_name=state.get("db_name"))

        return {"retrieval_result": result.__dict__}


def retrieve_node(state: EasySQLState) -> dict:
    """Legacy function wrapper for RetrieveNode."""
    node = RetrieveNode()
    return node(state)
