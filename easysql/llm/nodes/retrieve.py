"""
Retrieve Schema Node.

Wraps the existing SchemaRetrievalService.
"""
from functools import lru_cache
from typing import Optional

from easysql.config import get_settings
from easysql.llm.state import EasySQLState
from easysql.llm.nodes.base import BaseNode
from easysql.retrieval.schema_retrieval import SchemaRetrievalService
from easysql.writers.milvus_writer import MilvusVectorWriter
from easysql.writers.neo4j_writer import Neo4jSchemaWriter
from easysql.embeddings.embedding_service import EmbeddingService


@lru_cache(maxsize=1)
def get_retrieval_service() -> SchemaRetrievalService:
    """Get singleton SchemaRetrievalService instance.
    
    Uses lru_cache to ensure a single instance is reused.
    Properly initializes MilvusVectorWriter with required dependencies.
    
    Returns:
        Configured SchemaRetrievalService instance.
    """
    settings = get_settings()
    
    # Initialize EmbeddingService
    # Only accepts: model_name, device, normalize
    embedding_service = EmbeddingService(
        model_name=settings.embedding_model,
    )
    
    # Initialize MilvusVectorWriter with required parameters
    milvus = MilvusVectorWriter(
        uri=settings.milvus_uri,
        embedding_service=embedding_service,
        token=getattr(settings, 'milvus_token', None),
        collection_prefix=getattr(settings, 'milvus_collection_prefix', ''),
    )
    
    # Initialize Neo4jSchemaWriter with required parameters
    neo4j = Neo4jSchemaWriter(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=getattr(settings, 'neo4j_database', 'neo4j'),
    )
    
    return SchemaRetrievalService.from_settings(
        milvus=milvus,
        neo4j=neo4j,
        settings=settings,
    )


class RetrieveNode(BaseNode):
    """Node to retrieve schema based on query.
    
    Wraps SchemaRetrievalService with DI support.
    """
    
    def __init__(self, service: Optional[SchemaRetrievalService] = None):
        """Initialize the retrieve node.
        
        Args:
            service: Optional pre-configured SchemaRetrievalService. 
                    If None, will use singleton instance.
        """
        self._service = service
    
    @property
    def service(self) -> SchemaRetrievalService:
        """Get or lazily initialize the retrieval service."""
        if self._service is None:
            self._service = get_retrieval_service()
        return self._service
    
    def __call__(self, state: EasySQLState) -> dict:
        """Retrieve schema based on clarified query.
        
        Args:
            state: Current graph state.
            
        Returns:
            State updates with retrieval_result.
        """
        query = state["clarified_query"] or state["raw_query"]
        
        result = self.service.retrieve(
            question=query,
            db_name=state.get("db_name")
        )
        
        # Convert dataclass to dict for State compatibility (serialized)
        return {
            "retrieval_result": result.__dict__
        }


# Factory function for backward compatibility
def retrieve_node(state: EasySQLState) -> dict:
    """Legacy function wrapper for RetrieveNode."""
    node = RetrieveNode()
    return node(state)
