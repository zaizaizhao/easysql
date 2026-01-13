"""
Simplified factory for code context components.

Removed Neo4j dependency, uses LangChain-based chunking.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymilvus import MilvusClient

    from easysql.config import Settings
    from easysql.embeddings.embedding_service import EmbeddingService

from easysql.code_context.chunker import CodeChunker
from easysql.code_context.pipeline import CodeSyncPipeline
from easysql.code_context.retrieval import CodeRetrievalConfig, CodeRetrievalService
from easysql.code_context.storage import (
    CodeMilvusConfig,
    CodeMilvusReader,
    CodeMilvusWriter,
)
from easysql.code_context.utils import FileTracker


class CodeContextFactory:
    @staticmethod
    def create_milvus_config(database_name: str | None = None) -> CodeMilvusConfig:
        return CodeMilvusConfig(database_prefix=database_name or "")

    @staticmethod
    def create_writer(
        client: "MilvusClient",
        embedding_service: "EmbeddingService",
        database_name: str | None = None,
    ) -> CodeMilvusWriter:
        config = CodeContextFactory.create_milvus_config(database_name)
        return CodeMilvusWriter(
            client=client,
            embedding_service=embedding_service,
            config=config,
        )

    @staticmethod
    def create_reader(
        client: "MilvusClient",
        embedding_service: "EmbeddingService",
        database_name: str | None = None,
    ) -> CodeMilvusReader:
        config = CodeContextFactory.create_milvus_config(database_name)
        return CodeMilvusReader(
            client=client,
            embedding_service=embedding_service,
            config=config,
        )

    @staticmethod
    def create_chunker(
        chunk_size: int = 2000,
        chunk_overlap: int = 200,
        supported_languages: list[str] | None = None,
    ) -> CodeChunker:
        return CodeChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            supported_languages=supported_languages,
        )

    @staticmethod
    def create_retrieval_service(
        client: "MilvusClient",
        embedding_service: "EmbeddingService",
        settings: "Settings | None" = None,
        database_name: str | None = None,
    ) -> CodeRetrievalService:
        reader = CodeContextFactory.create_reader(
            client=client,
            embedding_service=embedding_service,
            database_name=database_name,
        )

        config = CodeRetrievalConfig()

        if settings:
            config.top_k = settings.code_context_search_top_k
            config.score_threshold = settings.code_context_score_threshold
            config.max_snippets = settings.code_context_max_snippets

        return CodeRetrievalService(milvus_reader=reader, config=config)

    @staticmethod
    def create_sync_pipeline(
        writer: CodeMilvusWriter,
        cache_dir: str | Path = ".code_context_cache",
        project_id: str = "default",
        chunk_size: int = 2000,
        chunk_overlap: int = 200,
    ) -> CodeSyncPipeline:
        cache_path = Path(cache_dir) / f"{project_id}_file_hashes.json"
        file_tracker = FileTracker(cache_path)

        chunker = CodeContextFactory.create_chunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        return CodeSyncPipeline(
            milvus_writer=writer,
            file_tracker=file_tracker,
            chunker=chunker,
        )

    @staticmethod
    def create_from_settings(
        client: "MilvusClient",
        embedding_service: "EmbeddingService",
        settings: "Settings | None" = None,
        database_name: str | None = None,
    ) -> tuple[CodeMilvusWriter, CodeMilvusReader, CodeRetrievalService]:
        if settings is None:
            from easysql.config import get_settings

            settings = get_settings()

        writer = CodeContextFactory.create_writer(
            client=client,
            embedding_service=embedding_service,
            database_name=database_name,
        )

        reader = CodeContextFactory.create_reader(
            client=client,
            embedding_service=embedding_service,
            database_name=database_name,
        )

        retrieval_service = CodeContextFactory.create_retrieval_service(
            client=client,
            embedding_service=embedding_service,
            settings=settings,
            database_name=database_name,
        )

        return writer, reader, retrieval_service
