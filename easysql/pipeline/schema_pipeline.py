"""
Schema processing pipeline for EasySql.

Orchestrates the complete flow from database schema extraction
to Neo4j graph storage and Milvus vector embedding.
"""

from dataclasses import dataclass, field

import easysql.extractors  # noqa: F401 - Register built-in extractors
from easysql.config import DatabaseConfig, Settings
from easysql.embeddings.embedding_service import EmbeddingService
from easysql.extractors.base import ExtractorFactory
from easysql.models.schema import DatabaseMeta
from easysql.repositories.milvus_repository import MilvusRepository
from easysql.repositories.neo4j_repository import Neo4jRepository
from easysql.utils.logger import get_logger, setup_logging
from easysql.writers.milvus_writer import MilvusVectorWriter
from easysql.writers.neo4j_writer import Neo4jSchemaWriter

logger = get_logger(__name__)


@dataclass
class PipelineStats:
    """Statistics from pipeline execution."""

    databases_processed: int = 0
    tables_extracted: int = 0
    columns_extracted: int = 0
    foreign_keys_extracted: int = 0
    neo4j_tables_written: int = 0
    neo4j_columns_written: int = 0
    neo4j_fks_written: int = 0
    milvus_tables_written: int = 0
    milvus_columns_written: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "databases_processed": self.databases_processed,
            "tables_extracted": self.tables_extracted,
            "columns_extracted": self.columns_extracted,
            "foreign_keys_extracted": self.foreign_keys_extracted,
            "neo4j_tables_written": self.neo4j_tables_written,
            "neo4j_columns_written": self.neo4j_columns_written,
            "neo4j_fks_written": self.neo4j_fks_written,
            "milvus_tables_written": self.milvus_tables_written,
            "milvus_columns_written": self.milvus_columns_written,
            "errors": self.errors,
        }


class SchemaPipeline:
    """
    Main pipeline for schema extraction and storage.

    Orchestrates:
    1. Database schema extraction (MySQL, PostgreSQL)
    2. Neo4j graph storage (tables, columns, relationships)
    3. Milvus vector embedding (semantic search)
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._neo4j_repo: Neo4jRepository | None = None
        self._milvus_repo: MilvusRepository | None = None
        self._neo4j_writer: Neo4jSchemaWriter | None = None
        self._milvus_writer: MilvusVectorWriter | None = None
        self._embedding_service: EmbeddingService | None = None

        setup_logging(
            level=settings.log_level,
            log_file=settings.log_file,
        )

    @property
    def neo4j_repo(self) -> Neo4jRepository:
        if self._neo4j_repo is None:
            self._neo4j_repo = Neo4jRepository(
                uri=self.settings.neo4j_uri,
                user=self.settings.neo4j_user,
                password=self.settings.neo4j_password,
                database=self.settings.neo4j_database,
            )
        return self._neo4j_repo

    @property
    def milvus_repo(self) -> MilvusRepository:
        if self._milvus_repo is None:
            self._milvus_repo = MilvusRepository(
                uri=self.settings.milvus_uri,
                token=self.settings.milvus_token,
                collection_prefix=self.settings.milvus_collection_prefix,
            )
        return self._milvus_repo

    @property
    def embedding_service(self) -> EmbeddingService:
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService.from_settings(self.settings)
        return self._embedding_service

    @property
    def neo4j_writer(self) -> Neo4jSchemaWriter:
        if self._neo4j_writer is None:
            self._neo4j_writer = Neo4jSchemaWriter(repository=self.neo4j_repo)
        return self._neo4j_writer

    @property
    def milvus_writer(self) -> MilvusVectorWriter:
        if self._milvus_writer is None:
            self._milvus_writer = MilvusVectorWriter(
                repository=self.milvus_repo,
                embedding_service=self.embedding_service,
            )
        return self._milvus_writer

    def run(
        self,
        databases: list[DatabaseConfig] | None = None,
        extract: bool = True,
        write_neo4j: bool = True,
        write_milvus: bool = True,
        drop_existing: bool = False,
    ) -> PipelineStats:
        """Run the complete pipeline."""
        stats = PipelineStats()

        if databases is None:
            databases = list(self.settings.databases.values())

        if not databases:
            logger.warning("No databases configured")
            stats.errors.append("No databases configured")
            return stats

        logger.info(f"Starting pipeline for {len(databases)} database(s)")

        db_metas: list[DatabaseMeta] = []
        if extract and self.settings.enable_schema_extraction:
            for db_config in databases:
                try:
                    meta = self._extract_database(db_config)
                    db_metas.append(meta)
                    stats.databases_processed += 1
                    stats.tables_extracted += len(meta.tables)
                    stats.columns_extracted += sum(len(t.columns) for t in meta.tables)
                    stats.foreign_keys_extracted += len(meta.foreign_keys)
                except Exception as e:
                    error_msg = f"Failed to extract {db_config.database}: {e}"
                    logger.error(error_msg)
                    stats.errors.append(error_msg)

        if write_neo4j and self.settings.enable_neo4j_write and db_metas:
            try:
                with self.neo4j_repo:
                    neo4j_stats = self._write_to_neo4j(db_metas, drop_existing)
                    stats.neo4j_tables_written = neo4j_stats["tables"]
                    stats.neo4j_columns_written = neo4j_stats["columns"]
                    stats.neo4j_fks_written = neo4j_stats["foreign_keys"]
            except Exception as e:
                error_msg = f"Failed to write to Neo4j: {e}"
                logger.error(error_msg)
                stats.errors.append(error_msg)

        if write_milvus and self.settings.enable_milvus_write and db_metas:
            try:
                with self.milvus_repo:
                    milvus_stats = self._write_to_milvus(db_metas, drop_existing)
                    stats.milvus_tables_written = milvus_stats["tables"]
                    stats.milvus_columns_written = milvus_stats["columns"]
            except Exception as e:
                error_msg = f"Failed to write to Milvus: {e}"
                logger.error(error_msg)
                stats.errors.append(error_msg)

        self._log_summary(stats)

        return stats

    def _extract_database(self, db_config: DatabaseConfig) -> DatabaseMeta:
        logger.info(f"Extracting schema from: {db_config.database} ({db_config.db_type})")

        extractor = ExtractorFactory.create(db_config)
        meta = extractor.extract_all()

        stats = meta.get_statistics()
        logger.info(
            f"Extracted: {stats['tables']} tables, "
            f"{stats['columns']} columns, {stats['foreign_keys']} FKs"
        )

        return meta

    def _write_to_neo4j(
        self,
        db_metas: list[DatabaseMeta],
        drop_existing: bool,
    ) -> dict:
        logger.info("Writing to Neo4j")

        stats = {"tables": 0, "columns": 0, "foreign_keys": 0}

        for meta in db_metas:
            if drop_existing:
                self.neo4j_writer.clear_database(meta.name)

            result = self.neo4j_writer.write_database(meta)
            stats["tables"] += result["tables"]
            stats["columns"] += result["columns"]
            stats["foreign_keys"] += result["foreign_keys"]

        logger.info(
            f"Neo4j write complete: {stats['tables']} tables, "
            f"{stats['columns']} columns, {stats['foreign_keys']} FKs"
        )

        return stats

    def _write_to_milvus(
        self,
        db_metas: list[DatabaseMeta],
        drop_existing: bool,
    ) -> dict:
        logger.info("Writing to Milvus")

        stats = {"tables": 0, "columns": 0}

        self.milvus_writer.create_table_collection(drop_existing=drop_existing)
        self.milvus_writer.create_column_collection(drop_existing=drop_existing)

        for meta in db_metas:
            tables_written = self.milvus_writer.write_table_embeddings(
                meta, batch_size=self.settings.batch_size
            )
            columns_written = self.milvus_writer.write_column_embeddings(
                meta, batch_size=self.settings.batch_size
            )
            stats["tables"] += tables_written
            stats["columns"] += columns_written

        logger.info(f"Milvus write complete: {stats['tables']} tables, {stats['columns']} columns")

        return stats

    def _log_summary(self, stats: PipelineStats) -> None:
        logger.info("=" * 60)
        logger.info("Pipeline Execution Summary")
        logger.info("=" * 60)
        logger.info(f"Databases processed: {stats.databases_processed}")
        logger.info(f"Tables extracted: {stats.tables_extracted}")
        logger.info(f"Columns extracted: {stats.columns_extracted}")
        logger.info(f"Foreign keys extracted: {stats.foreign_keys_extracted}")
        logger.info(f"Neo4j tables written: {stats.neo4j_tables_written}")
        logger.info(f"Neo4j columns written: {stats.neo4j_columns_written}")
        logger.info(f"Milvus tables written: {stats.milvus_tables_written}")
        logger.info(f"Milvus columns written: {stats.milvus_columns_written}")

        if stats.errors:
            logger.warning(f"Errors encountered: {len(stats.errors)}")
            for error in stats.errors:
                logger.error(f"  - {error}")
        else:
            logger.info("No errors encountered")

        logger.info("=" * 60)

    def close(self) -> None:
        if self._neo4j_repo:
            self._neo4j_repo.close()
        if self._milvus_repo:
            self._milvus_repo.close()
