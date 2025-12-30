"""
Milvus vector writer for EasySql.

Writes schema embeddings to Milvus vector database for semantic search.
Creates collections for tables and columns with their vector representations.
"""

from typing import Any, List

from pymilvus import MilvusClient, DataType

from easysql.embeddings.embedding_service import EmbeddingService
from easysql.models.schema import DatabaseMeta, TableMeta
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


class MilvusVectorWriter:
    """
    Milvus vector database writer for schema embeddings.

    Creates and populates vector collections:
    - table_embeddings: Table-level semantic vectors
    - column_embeddings: Column-level semantic vectors

    Usage:
        writer = MilvusVectorWriter(uri, embedding_service)
        writer.write_table_embeddings(db_meta)
        writer.write_column_embeddings(db_meta)
    """

    # Collection names
    TABLE_COLLECTION = "table_embeddings"
    COLUMN_COLLECTION = "column_embeddings"

    def __init__(
        self,
        uri: str,
        embedding_service: EmbeddingService,
        token: str | None = None,
    ):
        """
        Initialize Milvus writer.

        Args:
            uri: Milvus connection URI
            embedding_service: Service for generating embeddings
            token: Optional authentication token
        """
        self.uri = uri
        self.token = token
        self.embedding_service = embedding_service
        self._client: MilvusClient | None = None

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
        return self._client

    def create_table_collection(self, drop_existing: bool = False) -> None:
        """
        Create the table embeddings collection.

        Args:
            drop_existing: Whether to drop existing collection first
        """
        collection_name = self.TABLE_COLLECTION
        dim = self.embedding_service.dimension

        if self.client.has_collection(collection_name):
            if drop_existing:
                logger.warning(f"Dropping existing collection: {collection_name}")
                self.client.drop_collection(collection_name)
            else:
                logger.info(f"Collection already exists: {collection_name}")
                return

        logger.info(f"Creating collection: {collection_name} (dim={dim})")

        # Create schema
        schema = self.client.create_schema(auto_id=False, enable_dynamic_field=False)

        schema.add_field("id", DataType.VARCHAR, max_length=256, is_primary=True)
        schema.add_field("database_name", DataType.VARCHAR, max_length=128)
        schema.add_field("schema_name", DataType.VARCHAR, max_length=128)
        schema.add_field("table_name", DataType.VARCHAR, max_length=128)
        schema.add_field("chinese_name", DataType.VARCHAR, max_length=256)
        schema.add_field("description", DataType.VARCHAR, max_length=2048)
        schema.add_field("business_domain", DataType.VARCHAR, max_length=64)
        schema.add_field("system_type", DataType.VARCHAR, max_length=32)
        schema.add_field("core_columns_text", DataType.VARCHAR, max_length=4096)
        schema.add_field("row_count", DataType.INT64)
        schema.add_field("is_archive", DataType.BOOL)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dim)

        # Create index
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
        logger.info(f"Collection created: {collection_name}")

    def create_column_collection(self, drop_existing: bool = False) -> None:
        """
        Create the column embeddings collection.

        Args:
            drop_existing: Whether to drop existing collection first
        """
        collection_name = self.COLUMN_COLLECTION
        dim = self.embedding_service.dimension

        if self.client.has_collection(collection_name):
            if drop_existing:
                logger.warning(f"Dropping existing collection: {collection_name}")
                self.client.drop_collection(collection_name)
            else:
                logger.info(f"Collection already exists: {collection_name}")
                return

        logger.info(f"Creating collection: {collection_name} (dim={dim})")

        # Create schema
        schema = self.client.create_schema(auto_id=False, enable_dynamic_field=False)

        schema.add_field("id", DataType.VARCHAR, max_length=256, is_primary=True)
        schema.add_field("database_name", DataType.VARCHAR, max_length=128)
        schema.add_field("table_name", DataType.VARCHAR, max_length=128)
        schema.add_field("column_name", DataType.VARCHAR, max_length=128)
        schema.add_field("chinese_name", DataType.VARCHAR, max_length=256)
        schema.add_field("data_type", DataType.VARCHAR, max_length=64)
        schema.add_field("description", DataType.VARCHAR, max_length=1024)
        schema.add_field("is_pk", DataType.BOOL)
        schema.add_field("is_fk", DataType.BOOL)
        schema.add_field("is_indexed", DataType.BOOL)
        schema.add_field("business_domain", DataType.VARCHAR, max_length=64)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dim)

        # Create index
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
        logger.info(f"Collection created: {collection_name}")

    def write_table_embeddings(
        self,
        db_meta: DatabaseMeta,
        batch_size: int = 100,
    ) -> int:
        """
        Write table embeddings to Milvus.

        Args:
            db_meta: Database metadata containing tables
            batch_size: Batch size for insertion

        Returns:
            Number of tables written
        """
        logger.info(f"Writing table embeddings for {db_meta.name}")

        # Prepare data
        data_batch: List[dict] = []
        texts_batch: List[str] = []

        for table in db_meta.tables:
            table_id = table.get_id(db_meta.name)
            embed_text = table.get_embedding_text(db_meta.name)
            texts_batch.append(embed_text)

            data_batch.append({
                "id": table_id,
                "database_name": db_meta.name,
                "schema_name": table.schema_name,
                "table_name": table.name,
                "chinese_name": table.chinese_name or "",
                "description": (table.description or "")[:2048],
                "business_domain": table.business_domain or "",
                "system_type": db_meta.system_type,
                "core_columns_text": table.get_core_columns_text()[:4096],
                "row_count": table.row_count,
                "is_archive": table.is_archive,
            })

        if not data_batch:
            logger.warning("No tables to write")
            return 0

        # Generate embeddings in batch
        logger.info(f"Generating embeddings for {len(texts_batch)} tables")
        embeddings = self.embedding_service.encode_batch(texts_batch, batch_size=batch_size)

        # Add embeddings to data
        for i, embedding in enumerate(embeddings):
            data_batch[i]["embedding"] = embedding

        # Insert in batches
        total_inserted = 0
        for i in range(0, len(data_batch), batch_size):
            batch = data_batch[i : i + batch_size]
            self.client.insert(collection_name=self.TABLE_COLLECTION, data=batch)
            total_inserted += len(batch)
            logger.debug(f"Inserted {total_inserted}/{len(data_batch)} tables")

        logger.info(f"Table embeddings written: {total_inserted}")
        return total_inserted

    def write_column_embeddings(
        self,
        db_meta: DatabaseMeta,
        batch_size: int = 100,
    ) -> int:
        """
        Write column embeddings to Milvus.

        Args:
            db_meta: Database metadata containing tables with columns
            batch_size: Batch size for insertion

        Returns:
            Number of columns written
        """
        logger.info(f"Writing column embeddings for {db_meta.name}")

        # Prepare data
        data_batch: List[dict] = []
        texts_batch: List[str] = []

        for table in db_meta.tables:
            for col in table.columns:
                col_id = col.get_id(db_meta.name, table.schema_name, table.name)
                embed_text = col.get_embedding_text()
                texts_batch.append(embed_text)

                data_batch.append({
                    "id": col_id,
                    "database_name": db_meta.name,
                    "table_name": table.name,
                    "column_name": col.name,
                    "chinese_name": col.chinese_name or "",
                    "data_type": col.data_type,
                    "description": (col.description or "")[:1024],
                    "is_pk": col.is_pk,
                    "is_fk": col.is_fk,
                    "is_indexed": col.is_indexed,
                    "business_domain": table.business_domain or "",
                })

        if not data_batch:
            logger.warning("No columns to write")
            return 0

        # Generate embeddings in batch
        logger.info(f"Generating embeddings for {len(texts_batch)} columns")
        embeddings = self.embedding_service.encode_batch(
            texts_batch, batch_size=batch_size, show_progress=len(texts_batch) > 500
        )

        # Add embeddings to data
        for i, embedding in enumerate(embeddings):
            data_batch[i]["embedding"] = embedding

        # Insert in batches
        total_inserted = 0
        for i in range(0, len(data_batch), batch_size):
            batch = data_batch[i : i + batch_size]
            self.client.insert(collection_name=self.COLUMN_COLLECTION, data=batch)
            total_inserted += len(batch)
            logger.debug(f"Inserted {total_inserted}/{len(data_batch)} columns")

        logger.info(f"Column embeddings written: {total_inserted}")
        return total_inserted

    def search_tables(
        self,
        query: str,
        top_k: int = 10,
        filter_expr: str | None = None,
    ) -> List[dict]:
        """
        Search for similar tables by query text.

        Args:
            query: Search query text
            top_k: Number of results to return
            filter_expr: Optional filter expression

        Returns:
            List of matching tables with scores
        """
        query_embedding = self.embedding_service.encode(query)

        search_params = {"metric_type": "COSINE", "params": {"ef": 64}}

        results = self.client.search(
            collection_name=self.TABLE_COLLECTION,
            data=[query_embedding],
            limit=top_k,
            search_params=search_params,
            filter=filter_expr,
            output_fields=[
                "database_name", "table_name", "chinese_name",
                "description", "business_domain"
            ],
        )

        return [
            {
                "table_name": hit["entity"]["table_name"],
                "database_name": hit["entity"]["database_name"],
                "chinese_name": hit["entity"]["chinese_name"],
                "description": hit["entity"]["description"],
                "score": hit["distance"],
            }
            for hit in results[0]
        ]

    def search_columns(
        self,
        query: str,
        top_k: int = 20,
        table_filter: List[str] | None = None,
    ) -> List[dict]:
        """
        Search for similar columns by query text.

        Args:
            query: Search query text
            top_k: Number of results to return
            table_filter: Optional list of table names to filter

        Returns:
            List of matching columns with scores
        """
        query_embedding = self.embedding_service.encode(query)

        search_params = {"metric_type": "COSINE", "params": {"ef": 64}}

        filter_expr = None
        if table_filter:
            tables_str = ", ".join(f'"{t}"' for t in table_filter)
            filter_expr = f"table_name in [{tables_str}]"

        results = self.client.search(
            collection_name=self.COLUMN_COLLECTION,
            data=[query_embedding],
            limit=top_k,
            search_params=search_params,
            filter=filter_expr,
            output_fields=[
                "database_name", "table_name", "column_name",
                "chinese_name", "data_type", "is_pk", "is_fk"
            ],
        )

        return [
            {
                "table_name": hit["entity"]["table_name"],
                "column_name": hit["entity"]["column_name"],
                "chinese_name": hit["entity"]["chinese_name"],
                "data_type": hit["entity"]["data_type"],
                "is_pk": hit["entity"]["is_pk"],
                "is_fk": hit["entity"]["is_fk"],
                "score": hit["distance"],
            }
            for hit in results[0]
        ]

    def get_collection_stats(self) -> dict:
        """Get statistics for all collections."""
        stats = {}

        for collection_name in [self.TABLE_COLLECTION, self.COLUMN_COLLECTION]:
            if self.client.has_collection(collection_name):
                info = self.client.get_collection_stats(collection_name)
                stats[collection_name] = {
                    "row_count": info.get("row_count", 0),
                }
            else:
                stats[collection_name] = {"exists": False}

        return stats

    def __enter__(self) -> "MilvusVectorWriter":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
