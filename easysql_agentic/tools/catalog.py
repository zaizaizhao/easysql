"""Adapters to existing semantic retrieval and configured data-plane metadata."""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect

from easysql.agent_tools.runtime import get_schema_tool_service
from easysql.federation import DatabaseScope
from easysql.infrastructure import get_data_plane_engine_registry
from easysql.retrieval.runtime import get_retrieval_runtime
from easysql_agentic.knowledge.models import TableRef


class Catalog:
    def __init__(self, scope: DatabaseScope) -> None:
        self.scope = scope

    def require_table(self, table_id: str) -> TableRef:
        ref = TableRef.parse(table_id)
        target = self.scope.require_primary(ref.database)
        if ref.schema_name != target.schema:
            raise ValueError("Table is outside the configured schema")
        return ref

    def search_tables(self, query: str, db_name: str, top_k: int) -> dict[str, Any]:
        self.scope.require_primary(db_name)
        return get_schema_tool_service().search_tables(db_name=db_name, query=query, top_k=top_k)

    def search_columns(self, query: str, db_name: str, top_k: int) -> dict[str, Any]:
        self.scope.require_primary(db_name)
        return get_schema_tool_service().search_columns(db_name=db_name, query=query, top_k=top_k)

    def list_tables(self, db_name: str, offset: int = 0) -> dict[str, Any]:
        target = self.scope.require_primary(db_name)
        engine = get_data_plane_engine_registry().get_engine(target.config)
        names = sorted(inspect(engine).get_table_names(schema=target.schema))
        return {
            "tables": [
                f"{target.name}.{target.schema}.{name}" for name in names[offset : offset + 40]
            ],
            "next_offset": offset + 40 if len(names) > offset + 40 else None,
        }

    def table_schema(self, table_id: str) -> dict[str, Any]:
        ref = self.require_table(table_id)
        target = self.scope.require_primary(ref.database)
        inspector = inspect(get_data_plane_engine_registry().get_engine(target.config))
        columns = inspector.get_columns(ref.table, schema=ref.schema_name)
        pk = inspector.get_pk_constraint(ref.table, schema=ref.schema_name)
        fks = inspector.get_foreign_keys(ref.table, schema=ref.schema_name)
        return {
            "table_id": ref.id,
            "columns": [
                {
                    "name": column["name"],
                    "data_type": str(column["type"]),
                    "nullable": column.get("nullable"),
                    "description": column.get("comment"),
                }
                for column in columns
            ],
            "primary_key": pk.get("constrained_columns", []),
            "foreign_keys": fks,
        }

    def expand_tables(self, db_name: str, table_names: list[str], depth: int) -> dict[str, Any]:
        self.scope.require_primary(db_name)
        return get_schema_tool_service().expand_related_tables(
            db_name=db_name, seed_tables=table_names, max_depth=depth
        )

    def physical_edges(self, table_ids: list[str]) -> list[dict[str, Any]]:
        reader = get_retrieval_runtime().neo4j_reader
        with reader.driver.session(database=reader.database) as session:
            result = session.run(
                "MATCH (a:Table)-[r:FOREIGN_KEY]-(b:Table) "
                "WHERE a.id IN $ids AND a.project_namespace=$namespace "
                "AND b.project_namespace=$namespace AND b.database IN $databases "
                "RETURN DISTINCT startNode(r).id AS source_table, endNode(r).id AS target_table, "
                "r.constraint_name AS name, coalesce(r.from_columns,[r.fk_column]) AS source_columns, "
                "coalesce(r.to_columns,[r.pk_column]) AS target_columns LIMIT 201",
                ids=table_ids,
                namespace=reader.project_namespace,
                databases=self.scope.names,
            )
            return [
                {
                    "id": f"fk:{row['source_table']}:{row['name']}",
                    "source_table": row["source_table"],
                    "target_table": row["target_table"],
                    "column_pairs": [
                        {"source": a, "target": b}
                        for a, b in zip(row["source_columns"], row["target_columns"], strict=True)
                    ],
                    "kind": "physical_foreign_key",
                }
                for row in result
            ]

    def examples(self, query: str) -> list[dict[str, Any]]:
        reader = get_retrieval_runtime().few_shot_reader
        examples = []
        for db_name in self.scope.names:
            for item in reader.search_similar(query=query, db_name=db_name, top_k=2, min_score=0.5):
                examples.append(
                    {
                        "database": db_name,
                        "question": item.question,
                        "sql": item.sql,
                        "tables_used": item.tables_used,
                        "explanation": item.explanation,
                    }
                )
        return examples[:6]
