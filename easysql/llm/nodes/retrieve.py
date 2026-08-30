from __future__ import annotations

from typing import TYPE_CHECKING, Any

from easysql.llm.nodes.base import BaseNode
from easysql.llm.state import EasySQLState
from easysql.retrieval.runtime import get_retrieval_runtime
from easysql.retrieval.schema_retrieval import SchemaRetrievalService
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.types import StreamWriter

logger = get_logger(__name__)


def get_retrieval_service() -> SchemaRetrievalService:
    return get_retrieval_runtime().schema_retrieval


class RetrieveNode(BaseNode):
    def __init__(self, service: SchemaRetrievalService | None = None):
        self._service = service

    @property
    def service(self) -> SchemaRetrievalService:
        if self._service is None:
            self._service = get_retrieval_service()
        return self._service

    def __call__(
        self,
        state: EasySQLState,
        config: RunnableConfig | None = None,
        *,
        writer: StreamWriter | None = None,
    ) -> dict[Any, Any]:
        clarified_query = state.get("clarified_query")
        query = clarified_query or state["raw_query"]

        initial_tables_by_db: dict[str, list[dict[str, Any]]] | None = None
        schema_hint = state.get("schema_hint")
        raw_query = state["raw_query"]
        if schema_hint and (not clarified_query or clarified_query == raw_query):
            initial_tables_by_db = {}
            for table in schema_hint["tables"]:
                database_name = table.get("database_name") or state.get("db_name")
                if not database_name:
                    continue
                raw_name = table.get("qualified_table_id", table["name"]).split(".")[-1]
                initial_table = {
                    "name": raw_name,
                    "score": table["score"],
                    "chinese_name": table.get("chinese_name"),
                    "description": table.get("description"),
                }
                if table.get("schema_name"):
                    initial_table["schema_name"] = table["schema_name"]
                initial_tables_by_db.setdefault(database_name.lower(), []).append(initial_table)

        db_names = state.get("db_names") or (
            [state["db_name"]] if state.get("db_name") else []
        )
        if not db_names:
            return {"error": "No database selected for retrieval"}
        result = self.service.retrieve_databases(
            question=query,
            db_names=db_names,
            initial_tables_by_db=initial_tables_by_db,
        )

        return {"retrieval_result": result.__dict__}


def retrieve_node(
    state: EasySQLState,
    config: RunnableConfig | None = None,
    *,
    writer: StreamWriter | None = None,
) -> dict[Any, Any]:
    node = RetrieveNode()
    return node(state, config, writer=writer)
