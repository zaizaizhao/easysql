"""
Retrieve Hint Node.

Provides schema context for the analyze node (plan mode only).
Retrieves tables + key columns + semantic columns to enable precise clarification questions.
"""

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from easysql.config import get_settings
from easysql.embeddings.embedding_service import EmbeddingService
from easysql.llm.nodes.base import BaseNode
from easysql.llm.state import EasySQLState, SchemaHintDict, SchemaHintTable, SchemaHintColumn
from easysql.readers.milvus_reader import MilvusSchemaReader
from easysql.readers.neo4j_reader import Neo4jSchemaReader
from easysql.repositories.milvus_repository import MilvusRepository
from easysql.repositories.neo4j_repository import Neo4jRepository

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.types import StreamWriter

TIME_DATA_TYPES = {"date", "datetime", "timestamp", "time", "year"}


@lru_cache(maxsize=1)
def _get_readers() -> tuple[MilvusSchemaReader, Neo4jSchemaReader]:
    settings = get_settings()

    embedding_service = EmbeddingService.from_settings(settings)
    milvus_repo = MilvusRepository(
        uri=settings.milvus_uri,
        token=settings.milvus_token,
        collection_prefix=settings.milvus_collection_prefix,
    )
    milvus_repo.connect()
    milvus_reader = MilvusSchemaReader(
        repository=milvus_repo,
        embedding_service=embedding_service,
    )

    neo4j_repo = Neo4jRepository(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )
    neo4j_repo.connect()
    neo4j_reader = Neo4jSchemaReader(repository=neo4j_repo)

    return milvus_reader, neo4j_reader


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
        db_name = state.get("db_name")

        table_results = self.milvus_reader.search_tables(
            query=query,
            top_k=self._table_top_k,
        )
        table_names = [r["table_name"] for r in table_results]

        table_columns = {}
        if table_names:
            table_columns = self.neo4j_reader.get_table_columns(
                table_names=table_names,
                db_name=db_name,
            )
        key_columns_map = self._extract_key_columns(table_columns)

        tables: list[SchemaHintTable] = [
            SchemaHintTable(
                name=r["table_name"],
                chinese_name=r.get("chinese_name"),
                description=r.get("description"),
                score=r.get("score", 0.0),
                key_columns=key_columns_map.get(r["table_name"], []),
            )
            for r in table_results
        ]

        semantic_columns: list[SchemaHintColumn] = []
        if table_names:
            col_results = self.milvus_reader.search_columns(
                query=query,
                top_k=self._column_top_k,
                table_filter=table_names,
            )
            for c in col_results:
                semantic_columns.append(
                    SchemaHintColumn(
                        table_name=c["table_name"],
                        column_name=c["column_name"],
                        chinese_name=c.get("chinese_name"),
                        data_type=c.get("data_type") or "unknown",
                        is_pk=bool(c.get("is_pk")),
                        is_fk=bool(c.get("is_fk")),
                        is_time=_is_time_type(c.get("data_type")),
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
