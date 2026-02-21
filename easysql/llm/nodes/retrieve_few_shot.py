"""
Retrieve Few-Shot Node.

Retrieves similar Q&A examples from Milvus for in-context learning.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from easysql.config import get_settings
from easysql.embeddings.embedding_service import EmbeddingService
from easysql.llm.nodes.base import BaseNode
from easysql.llm.state import EasySQLState, FewShotExampleDict
from easysql.readers.few_shot_reader import FewShotReader
from easysql.repositories.milvus_repository import MilvusRepository
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.types import StreamWriter

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_few_shot_reader() -> FewShotReader:
    """Get or create a cached FewShotReader instance."""
    settings = get_settings()

    embedding_service = EmbeddingService.from_settings(settings)

    milvus_repo = MilvusRepository(
        uri=settings.milvus_uri,
        token=settings.milvus_token,
        collection_prefix=settings.milvus_collection_prefix,
    )
    milvus_repo.connect()

    return FewShotReader(
        repository=milvus_repo,
        embedding_service=embedding_service,
        collection_name=settings.few_shot_collection_name,
    )


class RetrieveFewShotNode(BaseNode):
    """Node to retrieve few-shot examples from Milvus.

    Searches for semantically similar Q&A pairs based on the user's question.
    Results are stored in state.few_shot_examples for use in context building.
    """

    def __init__(self, reader: FewShotReader | None = None):
        """Initialize the retrieve few-shot node.

        Args:
            reader: Optional pre-configured FewShotReader.
                   If None, will use cached reader.
        """
        self._reader = reader

    @property
    def reader(self) -> FewShotReader:
        """Get or lazily initialize the few-shot reader."""
        if self._reader is None:
            self._reader = get_few_shot_reader()
        return self._reader

    def __call__(
        self,
        state: EasySQLState,
        config: "RunnableConfig | None" = None,
        *,
        writer: "StreamWriter | None" = None,
    ) -> dict[Any, Any]:
        """Retrieve few-shot examples based on the user's question.

        Args:
            state: Current graph state.
            config: Optional runnable config.
            writer: Optional stream writer.

        Returns:
            State updates with few_shot_examples.
        """
        settings = get_settings()

        if not settings.few_shot_enabled:
            logger.debug("Few-shot learning disabled, skipping retrieval")
            return {"few_shot_examples": None}

        query = state.get("clarified_query") or state["raw_query"]
        db_name = state.get("db_name")

        if not db_name:
            logger.warning("No db_name in state, cannot retrieve few-shot examples")
            return {"few_shot_examples": None}

        try:
            results = self.reader.search_similar(
                query=query,
                db_name=db_name,
                top_k=settings.few_shot_max_examples,
                min_score=settings.few_shot_min_similarity,
            )

            if not results:
                logger.debug(f"No few-shot examples found for query: {query[:50]}...")
                return {"few_shot_examples": None}

            examples: list[FewShotExampleDict] = [
                {
                    "question": r.question,
                    "sql": r.sql,
                    "tables_used": r.tables_used,
                    "explanation": r.explanation if r.explanation else None,
                }
                for r in results
            ]

            logger.info(
                f"Retrieved {len(examples)} few-shot examples "
                f"(scores: {[f'{r.score:.2f}' for r in results]})"
            )

            return {"few_shot_examples": examples}

        except Exception as e:
            logger.error(f"Failed to retrieve few-shot examples: {e}")
            return {"few_shot_examples": None}


def retrieve_few_shot_node(
    state: EasySQLState,
    config: "RunnableConfig | None" = None,
    *,
    writer: "StreamWriter | None" = None,
) -> dict[Any, Any]:
    """Legacy function wrapper for RetrieveFewShotNode."""
    node = RetrieveFewShotNode()
    return node(state, config, writer=writer)


def reset_few_shot_reader_cache() -> None:
    cache_info_fn = getattr(get_few_shot_reader, "cache_info", None)
    should_close = False
    if callable(cache_info_fn):
        should_close = getattr(cache_info_fn(), "currsize", 0) > 0

    if should_close:
        reader = get_few_shot_reader()
        repository = getattr(reader, "_repo", None)
        if repository is not None and hasattr(repository, "close"):
            repository.close()

    get_few_shot_reader.cache_clear()


def warm_few_shot_reader_cache() -> None:
    get_few_shot_reader()
