"""
Retrieve Hint Node.

Provides schema context for the analyze node (plan mode only).
Retrieves tables + key columns + semantic columns to enable precise clarification questions.
"""

from typing import TYPE_CHECKING, Any

from easysql.config import get_settings
from easysql.federation import DatabaseScope
from easysql.llm.nodes.base import BaseNode
from easysql.llm.state import EasySQLState, SchemaHintColumn, SchemaHintDict, SchemaHintTable
from easysql.readers.milvus_reader import MilvusSchemaReader
from easysql.readers.neo4j_reader import Neo4jSchemaReader
from easysql.retrieval.runtime import get_retrieval_runtime

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.types import StreamWriter

TIME_DATA_TYPES = {"date", "datetime", "timestamp", "time", "year"}


def _get_readers() -> tuple[MilvusSchemaReader, Neo4jSchemaReader]:
    runtime = get_retrieval_runtime()
    return runtime.milvus_reader, runtime.neo4j_reader


def _is_time_type(data_type: str | None) -> bool:
    if not data_type:
        return False
    dt_lower = data_type.lower()
    return any(t in dt_lower for t in TIME_DATA_TYPES)


class RetrieveHintNode(BaseNode):
    """Schema retrieval for analyze node context.

    Retrieves:
    1. Top-k tables (from Milvus semantic search)
    2. Key columns per table (PK, FK, time fields from Neo4j)
    3. Semantic columns (from Milvus column search)
    """

    def __init__(
        self,
        milvus_reader: MilvusSchemaReader | None = None,
        neo4j_reader: Neo4jSchemaReader | None = None,
        table_top_k: int = 5,
        column_top_k: int = 10,
    ):
        self._milvus_reader = milvus_reader
        self._neo4j_reader = neo4j_reader
        self._table_top_k = table_top_k
        self._column_top_k = column_top_k

    @property
    def milvus_reader(self) -> MilvusSchemaReader:
        if self._milvus_reader is None:
            self._milvus_reader, self._neo4j_reader = _get_readers()
        return self._milvus_reader

    @property
    def neo4j_reader(self) -> Neo4jSchemaReader:
        if self._neo4j_reader is None:
            self._milvus_reader, self._neo4j_reader = _get_readers()
        return self._neo4j_reader

    def _extract_key_columns(
        self, table_columns: dict[str, list[dict]]
    ) -> dict[str, list[SchemaHintColumn]]:
        key_cols: dict[str, list[SchemaHintColumn]] = {}
        for table_name, columns in table_columns.items():
            key_cols[table_name] = []
            for col in columns:
                is_time = _is_time_type(col.get("data_type"))
                is_key = col.get("is_pk") or col.get("is_fk") or is_time
                if is_key:
                    key_cols[table_name].append(
                        SchemaHintColumn(
                            table_name=table_name,
                            column_name=col["name"],
                            chinese_name=col.get("chinese_name"),
                            data_type=col.get("data_type") or "unknown",
                            is_pk=bool(col.get("is_pk")),
                            is_fk=bool(col.get("is_fk")),
                            is_time=is_time,
                        )
                    )
        return key_cols

    def __call__(
        self,
        state: EasySQLState,
        config: "RunnableConfig | None" = None,
        *,
        writer: "StreamWriter | None" = None,
    ) -> dict[Any, Any]:
        query = state["raw_query"]
        scope = DatabaseScope.resolve(
            get_settings(),
            db_names=state.get("db_names"),
            db_name=state.get("db_name"),
        )
        tables: list[SchemaHintTable] = []
        semantic_columns: list[SchemaHintColumn] = []
        for target in scope.targets:
            table_results = self.milvus_reader.search_tables(
                query=query,
                top_k=self._table_top_k,
                db_name=target.name,
            )
            table_names = [result["table_name"] for result in table_results]
            table_columns = (
                self.neo4j_reader.get_table_columns(
                    table_names=table_names,
                    db_name=target.name,
                )
                if table_names
                else {}
            )
            key_columns_map = self._extract_key_columns(table_columns)

            for result in table_results:
                table_name = result["table_name"]
                schema_name = result.get("schema_name") or target.schema
                qualified_id = f"{target.name}.{schema_name}.{table_name}"
                display_name = qualified_id if scope.is_federated else table_name
                key_columns = []
                for column in key_columns_map.get(table_name, []):
                    column_payload = dict(column)
                    column_payload.update(
                        {
                            "table_name": display_name,
                            "database_name": target.name,
                            "schema_name": schema_name,
                            "qualified_table_id": qualified_id,
                        }
                    )
                    key_columns.append(SchemaHintColumn(**column_payload))
                tables.append(
                    SchemaHintTable(
                        name=display_name,
                        chinese_name=result.get("chinese_name"),
                        description=result.get("description"),
                        score=result.get("score", 0.0),
                        key_columns=key_columns,
                        database_name=target.name,
                        schema_name=schema_name,
                        qualified_table_id=qualified_id,
                    )
                )

            if not table_names:
                continue
            col_results = self.milvus_reader.search_columns(
                query=query,
                top_k=self._column_top_k,
                db_name=target.name,
                table_filter=table_names,
            )
            for c in col_results:
                schema_name = c.get("schema_name") or target.schema
                qualified_id = f"{target.name}.{schema_name}.{c['table_name']}"
                semantic_columns.append(
                    SchemaHintColumn(
                        table_name=qualified_id if scope.is_federated else c["table_name"],
                        column_name=c["column_name"],
                        chinese_name=c.get("chinese_name"),
                        data_type=c.get("data_type") or "unknown",
                        is_pk=bool(c.get("is_pk")),
                        is_fk=bool(c.get("is_fk")),
                        is_time=_is_time_type(c.get("data_type")),
                        database_name=target.name,
                        schema_name=schema_name,
                        qualified_table_id=qualified_id,
                    )
                )

        schema_hint: SchemaHintDict = {
            "tables": tables,
            "semantic_columns": semantic_columns,
        }

        return {"schema_hint": schema_hint}


def retrieve_hint_node(
    state: EasySQLState,
    config: "RunnableConfig | None" = None,
    *,
    writer: "StreamWriter | None" = None,
) -> dict[Any, Any]:
    node = RetrieveHintNode()
    return node(state, config, writer=writer)
