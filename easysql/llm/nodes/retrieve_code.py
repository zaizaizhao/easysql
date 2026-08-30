"""Retrieve Code Node - Fetches code context after build_context."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from easysql.llm.nodes.base import BaseNode
from easysql.llm.state import EasySQLState
from easysql.retrieval.runtime import get_retrieval_runtime
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.types import StreamWriter

    from easysql.code_context.retrieval.code_retrieval import CodeRetrievalService

logger = get_logger(__name__)


def get_code_retrieval_service() -> CodeRetrievalService | None:
    try:
        return get_retrieval_runtime().code_retrieval
    except Exception as e:
        logger.warning(f"Failed to initialize code retrieval service: {e}")
        return None


class RetrieveCodeNode(BaseNode):
    def __init__(self, service: CodeRetrievalService | None = None):
        self._service = service
        self._service_checked = False

    @property
    def service(self) -> CodeRetrievalService | None:
        if not self._service_checked:
            if self._service is None:
                self._service = get_code_retrieval_service()
            self._service_checked = True
        return self._service

    def __call__(
        self,
        state: EasySQLState,
        config: RunnableConfig | None = None,
        *,
        writer: StreamWriter | None = None,
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
                # build_context runs after this node and renders the snippet
                # through CodeContextSection — no prompt patching here.
                return {"code_context": code_context}

        except Exception as e:
            logger.warning(f"Failed to retrieve code context: {e}")

        return {}


def retrieve_code_node(
    state: EasySQLState,
    config: RunnableConfig | None = None,
    *,
    writer: StreamWriter | None = None,
) -> dict[Any, Any]:
    node = RetrieveCodeNode()
    return node(state, config, writer=writer)
