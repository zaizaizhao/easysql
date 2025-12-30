"""
Schema processing pipeline for EasySql.

Orchestrates the complete flow from database schema extraction
to Neo4j graph storage and Milvus vector embedding.
"""

from dataclasses import dataclass, field
from typing import List

import easysql.extractors  # Register built-in extractors
from easysql.config import DatabaseConfig, Settings
from easysql.embeddings.embedding_service import EmbeddingService
from easysql.extractors.base import ExtractorFactory
from easysql.models.schema import DatabaseMeta
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
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
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

    Usage:
        settings = get_settings()
        pipeline = SchemaPipeline(settings)
        stats = pipeline.run()
    """

    def __init__(self, settings: Settings):
        """
        Initialize the pipeline.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self._neo4j_writer: Neo4jSchemaWriter | None = None
        self._milvus_writer: MilvusVectorWriter | None = None
        self._embedding_service: EmbeddingService | None = None

        # Setup logging
        setup_logging(
            level=settings.log_level,
            log_file=settings.log_file,
        )

    @property
    def neo4j_writer(self) -> Neo4jSchemaWriter:
        """Get Neo4j writer (lazy initialization)."""
        if self._neo4j_writer is None:
            self._neo4j_writer = Neo4jSchemaWriter(
                uri=self.settings.neo4j_uri,
                user=self.settings.neo4j_user,
                password=self.settings.neo4j_password,
            )
        return self._neo4j_writer

    @property
    def embedding_service(self) -> EmbeddingService:
        """Get embedding service (lazy initialization)."""
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService(
                model_name=self.settings.embedding_model,
            )
        return self._embedding_service

    @property
    def milvus_writer(self) -> MilvusVectorWriter:
        """Get Milvus writer (lazy initialization)."""
        if self._milvus_writer is None:
            self._milvus_writer = MilvusVectorWriter(
                uri=self.settings.milvus_uri,
                embedding_service=self.embedding_service,
                token=self.settings.milvus_token,
            )
        return self._milvus_writer

    # Main pipeline execution
    def run(
        self,
        databases: List[DatabaseConfig] | None = None,
        extract: bool = True,
        write_neo4j: bool = True,
        write_milvus: bool = True,
        drop_existing: bool = False,
    ) -> PipelineStats:
        """
        Run the complete pipeline.

        Args:
            databases: List of databases to process (default: from settings)
            extract: Whether to extract schema (default: True)
            write_neo4j: Whether to write to Neo4j (default: True)
            write_milvus: Whether to write to Milvus (default: True)
            drop_existing: Whether to drop existing data first

        Returns:
            Pipeline execution statistics
        """
        stats = PipelineStats()

        # Use databases from settings if not provided
        if databases is None:
            databases = self.settings.databases

        if not databases:
            logger.warning("No databases configured")
            stats.errors.append("No databases configured")
            return stats

        logger.info(f"Starting pipeline for {len(databases)} database(s)")

        # Extract all database schemas
        db_metas: List[DatabaseMeta] = []
        # 流程正式开始 action
        if extract and self.settings.enable_schema_extraction:
            for db_config in databases:
                try:
                    meta = self._extract_database(db_config)
                    db_metas.append(meta)
                    stats.databases_processed += 1
                    stats.tables_extracted += len(meta.tables)
                    stats.columns_extracted += sum(
                        len(t.columns) for t in meta.tables
                    )
                    stats.foreign_keys_extracted += len(meta.foreign_keys)
                except Exception as e:
                    error_msg = f"Failed to extract {db_config.database}: {e}"
                    logger.error(error_msg)
                    stats.errors.append(error_msg)

        # Write to Neo4j
        if write_neo4j and self.settings.enable_neo4j_write and db_metas:
            try:
                neo4j_stats = self._write_to_neo4j(db_metas, drop_existing)
                stats.neo4j_tables_written = neo4j_stats["tables"]
                stats.neo4j_columns_written = neo4j_stats["columns"]
                stats.neo4j_fks_written = neo4j_stats["foreign_keys"]
            except Exception as e:
                error_msg = f"Failed to write to Neo4j: {e}"
                logger.error(error_msg)
                stats.errors.append(error_msg)

        # Write to Milvus
        if write_milvus and self.settings.enable_milvus_write and db_metas:
            try:
                milvus_stats = self._write_to_milvus(db_metas, drop_existing)
                stats.milvus_tables_written = milvus_stats["tables"]
                stats.milvus_columns_written = milvus_stats["columns"]
            except Exception as e:
                error_msg = f"Failed to write to Milvus: {e}"
                logger.error(error_msg)
                stats.errors.append(error_msg)

        # Log summary
        self._log_summary(stats)

        return stats

    def _extract_database(self, db_config: DatabaseConfig) -> DatabaseMeta:
        """Extract schema from a single database."""
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
        db_metas: List[DatabaseMeta],
        drop_existing: bool,
    ) -> dict:
        """Write all database metadata to Neo4j."""
        logger.info("Writing to Neo4j")

        stats = {"tables": 0, "columns": 0, "foreign_keys": 0}

        with self.neo4j_writer as writer:
            for meta in db_metas:
                if drop_existing:
                    writer.clear_database(meta.name)

                result = writer.write_database(meta)
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
        db_metas: List[DatabaseMeta],
        drop_existing: bool,
    ) -> dict:
        """Write all embeddings to Milvus."""
        logger.info("Writing to Milvus")

        stats = {"tables": 0, "columns": 0}

        with self.milvus_writer as writer:
            # Create collections
            writer.create_table_collection(drop_existing=drop_existing)
            writer.create_column_collection(drop_existing=drop_existing)

            # Write embeddings for each database
            for meta in db_metas:
                tables_written = writer.write_table_embeddings(
                    meta, batch_size=self.settings.batch_size
                )
                columns_written = writer.write_column_embeddings(
                    meta, batch_size=self.settings.batch_size
                )
                stats["tables"] += tables_written
                stats["columns"] += columns_written

        logger.info(
            f"Milvus write complete: {stats['tables']} tables, "
            f"{stats['columns']} columns"
        )

        return stats

    def _log_summary(self, stats: PipelineStats) -> None:
        """Log pipeline execution summary."""
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
        """Close all connections."""
        if self._neo4j_writer:
            self._neo4j_writer.close()
        if self._milvus_writer:
            self._milvus_writer.close()
