"""
Milvus Repository - Connection management for Milvus.

Provides a shared connection layer used by both MilvusSchemaReader and MilvusVectorWriter.
"""

from pymilvus import MilvusClient

from easysql.utils.logger import get_logger

logger = get_logger(__name__)


class MilvusRepository:
    """
    Milvus connection manager.

    Manages the Milvus client lifecycle and provides collection access
    for both read and write operations.
    """

    TABLE_COLLECTION_BASE = "table_embeddings"
    COLUMN_COLLECTION_BASE = "column_embeddings"

    def __init__(
        self,
        uri: str,
        token: str | None = None,
        collection_prefix: str = "",
    ):
        self.uri = uri
        self.token = token
        self.collection_prefix = collection_prefix
        self._client: MilvusClient | None = None

    @property
    def table_collection(self) -> str:
        """Get table collection name with optional prefix."""
        if self.collection_prefix:
            return f"{self.collection_prefix}_table_embeddings"
        return self.TABLE_COLLECTION_BASE

    @property
    def column_collection(self) -> str:
        """Get column collection name with optional prefix."""
        if self.collection_prefix:
            return f"{self.collection_prefix}_column_embeddings"
        return self.COLUMN_COLLECTION_BASE

    def connect(self) -> None:
        """Establish connection to Milvus."""
        try:
            if self.token:
                self._client = MilvusClient(uri=self.uri, token=self.token)
            else:
                self._client = MilvusClient(uri=self.uri)
            logger.info(f"Connected to Milvus: {self.uri}")
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            raise ConnectionError(f"Milvus connection failed: {e}") from e

    def close(self) -> None:
        """Close Milvus connection."""
        if self._client:
            self._client.close()
            self._client = None
            logger.debug("Milvus connection closed")

    @property
    def client(self) -> MilvusClient:
        """Get the Milvus client, connecting if necessary."""
        if not self._client:
            self.connect()
        assert self._client is not None
        return self._client

    def __enter__(self) -> "MilvusRepository":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
