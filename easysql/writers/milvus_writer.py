"""
Milvus vector writer for EasySql.

Writes schema embeddings to Milvus vector database for semantic search.
Creates collections for tables and columns with their vector representations.
"""

from pymilvus import DataType

from easysql.embeddings.embedding_service import EmbeddingService
from easysql.models.schema import DatabaseMeta
from easysql.repositories.milvus_repository import MilvusRepository
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


class MilvusVectorWriter:
    """
    Milvus vector database writer for schema embeddings.

    Creates and populates vector collections:
    - table_embeddings: Table-level semantic vectors
    - column_embeddings: Column-level semantic vectors
    """

    def __init__(self, repository: MilvusRepository, embedding_service: EmbeddingService):
        self._repo = repository
        self._embedding_service = embedding_service

    @property
    def client(self):
        return self._repo.client

    @property
    def table_collection(self) -> str:
        return self._repo.table_collection

    @property
    def column_collection(self) -> str:
        return self._repo.column_collection

    @property
    def embedding_service(self) -> EmbeddingService:
        return self._embedding_service

    def create_table_collection(self, drop_existing: bool = False) -> None:
        """Create the table embeddings collection."""
        collection_name = self.table_collection
        dim = self._embedding_service.dimension

        if self.client.has_collection(collection_name):
            if drop_existing:
                logger.warning(f"Dropping existing collection: {collection_name}")
                self.client.drop_collection(collection_name)
            else:
                logger.info(f"Collection already exists: {collection_name}")
                return

        logger.info(f"Creating collection: {collection_name} (dim={dim})")

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
        """Create the column embeddings collection."""
        collection_name = self.column_collection
        dim = self._embedding_service.dimension

        if self.client.has_collection(collection_name):
            if drop_existing:
                logger.warning(f"Dropping existing collection: {collection_name}")
                self.client.drop_collection(collection_name)
            else:
                logger.info(f"Collection already exists: {collection_name}")
                return

        logger.info(f"Creating collection: {collection_name} (dim={dim})")

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
        """Write table embeddings to Milvus."""
        logger.info(f"Writing table embeddings for {db_meta.name}")

        data_batch: list[dict] = []
        texts_batch: list[str] = []

        for table in db_meta.tables:
            table_id = table.get_id(db_meta.name)
            embed_text = table.get_embedding_text(db_meta.name)
            texts_batch.append(embed_text)

            data_batch.append(
                {
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
                }
            )

        if not data_batch:
            logger.warning("No tables to write")
            return 0

        logger.info(f"Generating embeddings for {len(texts_batch)} tables")
        embeddings = self._embedding_service.encode_batch(texts_batch, batch_size=batch_size)

        for i, embedding in enumerate(embeddings):
            data_batch[i]["embedding"] = embedding

        total_inserted = 0
        for i in range(0, len(data_batch), batch_size):
            batch = data_batch[i : i + batch_size]
            self.client.insert(collection_name=self.table_collection, data=batch)
            total_inserted += len(batch)
            logger.debug(f"Inserted {total_inserted}/{len(data_batch)} tables")

        logger.info(f"Table embeddings written: {total_inserted}")
        return total_inserted

    def write_column_embeddings(
        self,
        db_meta: DatabaseMeta,
        batch_size: int = 100,
    ) -> int:
        """Write column embeddings to Milvus."""
        logger.info(f"Writing column embeddings for {db_meta.name}")

        data_batch: list[dict] = []
        texts_batch: list[str] = []

        for table in db_meta.tables:
            for col in table.columns:
                col_id = col.get_id(db_meta.name, table.schema_name, table.name)
                embed_text = col.get_embedding_text()
                texts_batch.append(embed_text)

                data_batch.append(
                    {
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
                    }
                )

        if not data_batch:
            logger.warning("No columns to write")
            return 0

        logger.info(f"Generating embeddings for {len(texts_batch)} columns")
        embeddings = self._embedding_service.encode_batch(
            texts_batch, batch_size=batch_size, show_progress=len(texts_batch) > 500
        )

        for i, embedding in enumerate(embeddings):
            data_batch[i]["embedding"] = embedding

        total_inserted = 0
        for i in range(0, len(data_batch), batch_size):
            batch = data_batch[i : i + batch_size]
            self.client.insert(collection_name=self.column_collection, data=batch)
            total_inserted += len(batch)
            logger.debug(f"Inserted {total_inserted}/{len(data_batch)} columns")

        logger.info(f"Column embeddings written: {total_inserted}")
        return total_inserted

    def __enter__(self) -> "MilvusVectorWriter":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass
