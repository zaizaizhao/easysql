"""Constrained read-only schema operations for agentic Text2SQL retrieval."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from easysql.config import Settings


MAX_QUERY_LENGTH = 2_000
MAX_TABLE_SEARCH_RESULTS = 10
MAX_COLUMN_SEARCH_RESULTS = 20
MAX_SEARCH_TABLE_FILTERS = 10
MAX_SCHEMA_TABLES = 8
MAX_EXPANSION_SEEDS = 5
MAX_EXPANSION_DEPTH = 2
MAX_JOIN_TABLES = 8
MAX_JOIN_HOPS = 5

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class DatabaseNotConfiguredError(ValueError):
    """Raised when an agent requests a logical database outside configured scope."""

    def __init__(self, db_name: str) -> None:
        super().__init__(f"Database is not configured: {db_name}")
        self.db_name = db_name


class MilvusSearchPort(Protocol):
    """Minimal Milvus interface required by the agent tool module."""

    def search_tables(
        self,
        query: str,
        top_k: int = 10,
        db_name: str | None = None,
        table_filter: list[str] | None = None,
    ) -> list[dict[str, Any]]: ...

    def search_columns(
        self,
        query: str,
        top_k: int = 20,
        db_name: str | None = None,
        table_filter: list[str] | None = None,
    ) -> list[dict[str, Any]]: ...


class Neo4jSchemaPort(Protocol):
    """Minimal Neo4j interface required by the agent tool module."""

    def get_table_columns(
        self,
        table_names: list[str],
        db_name: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]: ...

    def expand_with_related_tables(
        self,
        table_names: list[str],
        max_depth: int = 1,
        db_name: str | None = None,
    ) -> list[str]: ...

    def find_join_paths_for_tables(
        self,
        tables: list[str],
        max_hops: int = 5,
        db_name: str | None = None,
    ) -> list[dict[str, Any]]: ...


class SchemaToolService:
    """Expose small, evidence-oriented retrieval operations to external agents.

    The service intentionally does not call ``SchemaRetrievalService.retrieve``.
    Call order, semantic decomposition, graph expansion, and stopping decisions
    remain with the external agent. Database scope and resource budgets remain
    deterministic here.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        milvus: MilvusSearchPort,
        neo4j: Neo4jSchemaPort,
    ) -> None:
        self._settings = settings
        self._milvus = milvus
        self._neo4j = neo4j

    def describe_database_scope(self) -> dict[str, Any]:
        """Return credential-free metadata for every configured logical database."""
        databases: list[dict[str, Any]] = []
        for configured_name, config in self._settings.databases.items():
            name = str(configured_name).strip().lower()
            connection_name = getattr(config, "dblink_connection_name", None)
            if not connection_name:
                getter = getattr(config, "get_dblink_connection_name", None)
                connection_name = getter() if callable(getter) else f"{name}_conn"

            db_type = str(getattr(config, "db_type", "unknown")).lower()
            databases.append(
                {
                    "name": name,
                    "db_type": db_type,
                    "schema": config.get_default_schema(),
                    "system_type": getattr(config, "system_type", "UNKNOWN") or "UNKNOWN",
                    "description": getattr(config, "description", "") or "",
                    "dblink_connection_name": str(connection_name),
                    "supports_federation": db_type == "postgresql",
                }
            )

        return {"databases": databases, "total": len(databases)}

    def search_tables(
        self,
        *,
        db_name: str,
        query: str,
        top_k: int = 5,
        table_names: list[str] | None = None,
    ) -> dict[str, Any]:
        database, config = self._require_database(db_name)
        semantic_query = self._validate_query(query)
        self._validate_range("top_k", top_k, 1, MAX_TABLE_SEARCH_RESULTS)
        filters = self._validate_table_names(
            table_names or [],
            maximum=MAX_SEARCH_TABLE_FILTERS,
            allow_empty=True,
        )

        raw_matches = self._milvus.search_tables(
            semantic_query,
            top_k=top_k,
            db_name=database,
            table_filter=filters or None,
        )
        allowed_tables = set(filters)
        matches: list[dict[str, Any]] = []
        for raw in raw_matches:
            returned_database = str(raw.get("database_name") or "").strip().lower()
            table_name = str(raw.get("table_name") or "").strip()
            if returned_database != database or not table_name:
                continue
            if allowed_tables and table_name not in allowed_tables:
                continue

            matches.append(
                {
                    "database": database,
                    "schema": raw.get("schema_name") or config.get_default_schema(),
                    "table": table_name,
                    "chinese_name": raw.get("chinese_name"),
                    "description": raw.get("description"),
                    "business_domain": raw.get("business_domain"),
                    "rank": len(matches) + 1,
                    "similarity_score": float(raw.get("score") or 0.0),
                }
            )

        return {
            "database": database,
            "query": semantic_query,
            "matches": matches,
        }

    def search_columns(
        self,
        *,
        db_name: str,
        query: str,
        top_k: int = 10,
        table_names: list[str] | None = None,
    ) -> dict[str, Any]:
        database, config = self._require_database(db_name)
        semantic_query = self._validate_query(query)
        self._validate_range("top_k", top_k, 1, MAX_COLUMN_SEARCH_RESULTS)
        filters = self._validate_table_names(
            table_names or [],
            maximum=MAX_SEARCH_TABLE_FILTERS,
            allow_empty=True,
        )

        raw_matches = self._milvus.search_columns(
            semantic_query,
            top_k=top_k,
            db_name=database,
            table_filter=filters or None,
        )
        allowed_tables = set(filters)
        matches: list[dict[str, Any]] = []
        for raw in raw_matches:
            returned_database = str(raw.get("database_name") or "").strip().lower()
            table_name = str(raw.get("table_name") or "").strip()
            column_name = str(raw.get("column_name") or "").strip()
            if returned_database != database or not table_name or not column_name:
                continue
            if allowed_tables and table_name not in allowed_tables:
                continue

            matches.append(
                {
                    "database": database,
                    "schema": raw.get("schema_name") or config.get_default_schema(),
                    "table": table_name,
                    "column": column_name,
                    "qualified_table_id": raw.get("qualified_table_id"),
                    "chinese_name": raw.get("chinese_name"),
                    "data_type": raw.get("data_type"),
                    "is_primary_key": bool(raw.get("is_pk", False)),
                    "is_foreign_key": bool(raw.get("is_fk", False)),
                    "rank": len(matches) + 1,
                    "similarity_score": float(raw.get("score") or 0.0),
                }
            )

        return {
            "database": database,
            "query": semantic_query,
            "matches": matches,
        }

    def get_table_schema(
        self,
        *,
        db_name: str,
        table_names: list[str],
    ) -> dict[str, Any]:
        database, _ = self._require_database(db_name)
        requested = self._validate_table_names(table_names, maximum=MAX_SCHEMA_TABLES)
        raw_tables = self._neo4j.get_table_columns(requested, db_name=database)

        tables: list[dict[str, Any]] = []
        missing_tables: list[str] = []
        for table_name in requested:
            raw_columns = raw_tables.get(table_name)
            if raw_columns is None:
                missing_tables.append(table_name)
                continue
            columns = [self._normalize_column(column) for column in raw_columns]
            tables.append({"table": table_name, "columns": columns})

        return {
            "database": database,
            "tables": tables,
            "missing_tables": missing_tables,
        }

    def expand_related_tables(
        self,
        *,
        db_name: str,
        seed_tables: list[str],
        max_depth: int = 1,
    ) -> dict[str, Any]:
        database, _ = self._require_database(db_name)
        seeds = self._validate_table_names(seed_tables, maximum=MAX_EXPANSION_SEEDS)
        self._validate_range("max_depth", max_depth, 1, MAX_EXPANSION_DEPTH)

        raw_expanded = self._neo4j.expand_with_related_tables(
            seeds,
            max_depth=max_depth,
            db_name=database,
        )
        expanded = self._deduplicate([*seeds, *[str(name) for name in raw_expanded]])
        seed_set = set(seeds)
        added = [name for name in expanded if name not in seed_set]
        return {
            "database": database,
            "seed_tables": seeds,
            "added_tables": added,
            "expanded_tables": expanded,
            "max_depth": max_depth,
        }

    def find_join_paths(
        self,
        *,
        db_name: str,
        table_names: list[str],
        max_hops: int = 5,
    ) -> dict[str, Any]:
        database, _ = self._require_database(db_name)
        requested = self._validate_table_names(table_names, maximum=MAX_JOIN_TABLES)
        if len(requested) < 2:
            raise ValueError("table_names must contain at least two unique tables")
        self._validate_range("max_hops", max_hops, 1, MAX_JOIN_HOPS)

        raw_edges = self._neo4j.find_join_paths_for_tables(
            requested,
            max_hops=max_hops,
            db_name=database,
        )
        edges: list[dict[str, str]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for raw in raw_edges:
            edge = {
                "fk_table": str(raw.get("fk_table") or ""),
                "fk_column": str(raw.get("fk_column") or ""),
                "pk_table": str(raw.get("pk_table") or ""),
                "pk_column": str(raw.get("pk_column") or ""),
            }
            key = (
                edge["fk_table"],
                edge["fk_column"],
                edge["pk_table"],
                edge["pk_column"],
            )
            if not all(key) or key in seen:
                continue
            seen.add(key)
            edges.append(edge)

        requested_set = set(requested)
        bridge_tables = self._deduplicate(
            [
                table
                for edge in edges
                for table in (edge["fk_table"], edge["pk_table"])
                if table not in requested_set
            ]
        )
        return {
            "database": database,
            "requested_tables": requested,
            "bridge_tables": bridge_tables,
            "edges": edges,
            "max_hops": max_hops,
        }

    def _require_database(self, db_name: str) -> tuple[str, Any]:
        normalized = str(db_name).strip().lower()
        configured = {
            str(name).strip().lower(): config for name, config in self._settings.databases.items()
        }
        if normalized not in configured:
            raise DatabaseNotConfiguredError(normalized or str(db_name))
        return normalized, configured[normalized]

    @staticmethod
    def _validate_query(query: str) -> str:
        normalized = str(query).strip()
        if not normalized:
            raise ValueError("query must not be empty")
        if len(normalized) > MAX_QUERY_LENGTH:
            raise ValueError(f"query must contain at most {MAX_QUERY_LENGTH} characters")
        return normalized

    @classmethod
    def _validate_table_names(
        cls,
        table_names: list[str],
        *,
        maximum: int,
        allow_empty: bool = False,
    ) -> list[str]:
        normalized = cls._deduplicate([str(name).strip() for name in table_names])
        if not normalized and not allow_empty:
            raise ValueError("table names must not be empty")
        if len(normalized) > maximum:
            raise ValueError(f"at most {maximum} table names are allowed")
        invalid = [name for name in normalized if not _SAFE_IDENTIFIER.fullmatch(name)]
        if invalid:
            raise ValueError("table names must use unquoted letters, numbers, and underscores")
        return normalized

    @staticmethod
    def _validate_range(name: str, value: int, minimum: int, maximum: int) -> None:
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")

    @staticmethod
    def _deduplicate(values: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))

    @staticmethod
    def _normalize_column(raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": str(raw.get("name") or ""),
            "chinese_name": raw.get("chinese_name"),
            "data_type": raw.get("data_type"),
            "base_type": raw.get("base_type"),
            "is_primary_key": bool(raw.get("is_pk", False)),
            "is_foreign_key": bool(raw.get("is_fk", False)),
            "is_nullable": raw.get("is_nullable"),
            "is_indexed": raw.get("is_indexed"),
            "is_unique": raw.get("is_unique"),
            "description": raw.get("description"),
            "ordinal_position": raw.get("ordinal_position"),
        }
