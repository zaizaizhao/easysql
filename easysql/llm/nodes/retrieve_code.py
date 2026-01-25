"""Retrieve Code Node - Fetches code context after build_context."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from easysql.config import get_settings
from easysql.embeddings.embedding_service import EmbeddingService
from easysql.llm.nodes.base import BaseNode
from easysql.llm.state import EasySQLState
from easysql.repositories.milvus_repository import MilvusRepository
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.types import StreamWriter

    from easysql.code_context.retrieval.code_retrieval import CodeRetrievalService

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_code_retrieval_service() -> "CodeRetrievalService | None":
    settings = get_settings()

    if not settings.code_context_enabled:
        return None

    try:
        from easysql.code_context.factory import CodeContextFactory

        embedding_service = EmbeddingService.from_settings(settings)

        milvus_repo = MilvusRepository(
            uri=settings.milvus_uri,
            token=settings.milvus_token,
            collection_prefix=settings.milvus_collection_prefix,
        )
        milvus_repo.connect()

        return CodeContextFactory.create_retrieval_service(
            client=milvus_repo.client,
            embedding_service=embedding_service,
            settings=settings,
        )
    except Exception as e:
        logger.warning(f"Failed to initialize code retrieval service: {e}")
        return None


class RetrieveCodeNode(BaseNode):
    def __init__(self, service: "CodeRetrievalService | None" = None):
        self._service = service
        self._service_checked = False

    @property
    def service(self) -> "CodeRetrievalService | None":
        if not self._service_checked:
            if self._service is None:
                self._service = get_code_retrieval_service()
            self._service_checked = True
        return self._service

    def __call__(
        self,
        state: EasySQLState,
        config: "RunnableConfig | None" = None,
        *,
        writer: "StreamWriter | None" = None,
    ) -> dict[Any, Any]:
        if self.service is None:
            return {}

        query = state.get("clarified_query") or state["raw_query"]

        retrieval_result = state.get("retrieval_result")
        relevant_tables: list[str] = []
        if retrieval_result:
            relevant_tables = retrieval_result.get("tables", [])

        try:
            code_context = self.service.retrieve_formatted(
                question=query,
                relevant_tables=relevant_tables,
            )

            if code_context:
                context_output = state.get("context_output")
                if context_output:
                    updated_user_prompt = context_output["user_prompt"] + "\n\n" + code_context
                    return {
                        "context_output": {
                            **context_output,
                            "user_prompt": updated_user_prompt,
                        },
                        "code_context": code_context,
                    }

                return {"code_context": code_context}

        except Exception as e:
            logger.warning(f"Failed to retrieve code context: {e}")

        return {}


def retrieve_code_node(
    state: EasySQLState,
    config: "RunnableConfig | None" = None,
    *,
    writer: "StreamWriter | None" = None,
) -> dict[Any, Any]:
    node = RetrieveCodeNode()
    return node(state, config, writer=writer)
