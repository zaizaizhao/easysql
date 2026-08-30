"""
Schema Retrieval Service

The main service that orchestrates schema retrieval for Text2SQL.
Combines Milvus semantic search, Neo4j FK expansion, and configurable filters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from easysql.utils.logger import get_logger

from .base import FilterChain, FilterContext, NoOpFilter
from .bridge_filter import BridgeFilter
from .llm_filter import LLMFilter
from .semantic_filter import SemanticFilter

if TYPE_CHECKING:
    from easysql.config import Settings
    from easysql.readers.milvus_reader import MilvusSchemaReader
    from easysql.readers.neo4j_reader import Neo4jSchemaReader

logger = get_logger(__name__)


@dataclass
class RetrievalResult:
    """Result of schema retrieval."""

    tables: list[str]

    table_columns: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    table_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)

    semantic_columns: list[dict[str, Any]] = field(default_factory=list)

    join_paths: list[dict[str, str]] = field(default_factory=list)

    stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalConfig:
    """Configuration for schema retrieval."""

    search_top_k: int = 5

    expand_fk: bool = True

    expand_max_depth: int = 1

    semantic_filter_enabled: bool = True

    semantic_threshold: float = 0.4

    semantic_min_tables: int = 3

    bridge_protection_enabled: bool = True

    bridge_max_hops: int = 3

    core_tables: list[str] | None = None

    llm_filter_enabled: bool = False

    llm_filter_max_tables: int = 8

    llm_filter_model: str = "deepseek-chat"

    llm_filter_api_key: str | None = None

    llm_filter_api_base: str | None = None


class SchemaRetrievalService:
    """
    Service for retrieving relevant schema for Text2SQL.

    Workflow:
        1. Milvus semantic search → initial tables
        2. Neo4j FK expansion → expanded tables (optional)
        3. Semantic filter → remove low-score tables (optional)
        4. Bridge protection → add back essential bridge tables (optional)
        5. Return final tables + columns + JOIN paths
    """

    def __init__(
        self,
        milvus_reader: MilvusSchemaReader,
        neo4j_reader: Neo4jSchemaReader,
        config: RetrievalConfig | None = None,
        database_schemas: dict[str, str] | None = None,
    ):
        self._milvus = milvus_reader
        self._neo4j = neo4j_reader
        self.config = config or RetrievalConfig()
        self._database_schemas = {
            name.lower(): schema for name, schema in (database_schemas or {}).items()
        }

        self._filter_chain = self._build_filter_chain()

    def _build_filter_chain(self) -> FilterChain:
        chain = FilterChain()

        if self.config.semantic_filter_enabled:
            core_tables = set(self.config.core_tables) if self.config.core_tables else None
            chain.add(
                SemanticFilter(
                    threshold=self.config.semantic_threshold,
                    min_tables=self.config.semantic_min_tables,
                    core_tables=core_tables,
                )
            )

        if self.config.bridge_protection_enabled:
            protected = set(self.config.core_tables) if self.config.core_tables else set()
            chain.add(
                BridgeFilter(
                    neo4j_reader=self._neo4j,
                    max_hops=self.config.bridge_max_hops,
                    include_direct_neighbors=True,
                    protected_tables=protected,
                )
            )

        if self.config.llm_filter_enabled and self.config.llm_filter_api_key:
            chain.add(
                LLMFilter(
                    api_key=self.config.llm_filter_api_key,
                    api_base=self.config.llm_filter_api_base,
                    model=self.config.llm_filter_model,
                    max_tables=self.config.llm_filter_max_tables,
                )
            )

        if not chain.filters:
            chain.add(NoOpFilter())

        return chain

    @classmethod
    def from_settings(
        cls,
        milvus_reader: MilvusSchemaReader,
        neo4j_reader: Neo4jSchemaReader,
        settings: Settings | None = None,
    ) -> SchemaRetrievalService:
        """Create service from Settings (environment variables)."""
        if settings is None:
            from easysql.config import get_settings

            settings = get_settings()

        config = RetrievalConfig(
            search_top_k=settings.retrieval_search_top_k,
            expand_fk=settings.retrieval_expand_fk,
            expand_max_depth=settings.retrieval_expand_max_depth,
            semantic_filter_enabled=settings.semantic_filter_enabled,
            semantic_threshold=settings.semantic_filter_threshold,
            semantic_min_tables=settings.semantic_filter_min_tables,
            bridge_protection_enabled=settings.bridge_protection_enabled,
            core_tables=settings.core_tables_list,
            llm_filter_enabled=settings.llm_filter_enabled,
            llm_filter_max_tables=settings.llm_filter_max_tables,
            llm_filter_model=settings.llm_filter_model,
            llm_filter_api_key=settings.llm.openai_api_key,
            llm_filter_api_base=settings.llm.openai_api_base,
        )

        return cls(
            milvus_reader=milvus_reader,
            neo4j_reader=neo4j_reader,
            config=config,
            database_schemas={
                name: database.get_default_schema()
                for name, database in getattr(settings, "databases", {}).items()
            },
        )

    def retrieve_databases(
        self,
        question: str,
        db_names: list[str],
        initial_tables_by_db: dict[str, list[dict[str, Any]]] | None = None,
    ) -> RetrievalResult:
        """Retrieve one or many isolated database schemas.

        Single-database results deliberately retain the historical unqualified
        table names. Multi-database results use ``db.schema.table`` keys so
        tables with the same name cannot overwrite one another downstream.
        """
        normalized = list(dict.fromkeys(name.strip().lower() for name in db_names if name.strip()))
        if not normalized:
            raise ValueError("At least one database must be selected for retrieval")
        if len(normalized) == 1:
            name = normalized[0]
            return self.retrieve(
                question=question,
                db_name=name,
                initial_tables=(initial_tables_by_db or {}).get(name),
            )

        combined = RetrievalResult(tables=[])
        per_database_stats: dict[str, Any] = {}
        for db_name in normalized:
            result = self.retrieve(
                question=question,
                db_name=db_name,
                initial_tables=(initial_tables_by_db or {}).get(db_name),
            )
            qualified = self._qualify_result(result, db_name)
            combined.tables.extend(qualified.tables)
            combined.table_columns.update(qualified.table_columns)
            combined.table_metadata.update(qualified.table_metadata)
            combined.semantic_columns.extend(qualified.semantic_columns)
            combined.join_paths.extend(qualified.join_paths)
            per_database_stats[db_name] = result.stats

        combined.stats = {
            "mode": "multi_database",
            "databases": per_database_stats,
            "final": {
                "tables": len(combined.tables),
                "table_columns": sum(
                    len(columns) for columns in combined.table_columns.values()
                ),
                "semantic_columns": len(combined.semantic_columns),
                "join_paths": len(combined.join_paths),
            },
        }
        return combined

    def _qualify_result(self, result: RetrievalResult, db_name: str) -> RetrievalResult:
        default_schema = self._database_schemas.get(db_name.lower(), "public")
        name_map: dict[str, str] = {}
        metadata: dict[str, dict[str, Any]] = {}

        for table_name in result.tables:
            source_meta = dict(result.table_metadata.get(table_name, {}))
            schema_name = source_meta.get("schema_name") or default_schema
            qualified_id = f"{db_name}.{schema_name}.{table_name}"
            name_map[table_name] = qualified_id
            metadata[qualified_id] = {
                **source_meta,
                "database_name": db_name,
                "schema_name": schema_name,
                "table_name": table_name,
                "qualified_table_id": qualified_id,
            }

        table_columns: dict[str, list[dict[str, Any]]] = {}
        for table_name, columns in result.table_columns.items():
            qualified_id = name_map.get(
                table_name,
                f"{db_name}.{default_schema}.{table_name}",
            )
            schema_name = qualified_id.split(".", 2)[1]
            table_columns[qualified_id] = [
                {
                    **column,
                    "database_name": db_name,
                    "schema_name": schema_name,
                    "table_name": table_name,
                    "qualified_table_id": qualified_id,
                }
                for column in columns
            ]

        semantic_columns = []
        for column in result.semantic_columns:
            table_name = column.get("table_name", "")
            qualified_id = name_map.get(
                table_name,
                f"{db_name}.{default_schema}.{table_name}",
            )
            semantic_columns.append(
                {
                    **column,
                    "database_name": db_name,
                    "schema_name": qualified_id.split(".", 2)[1],
                    "qualified_table_id": qualified_id,
                }
            )

        join_paths = []
        for path in result.join_paths:
            fk_table = path.get("fk_table", "")
            pk_table = path.get("pk_table", "")
            join_paths.append(
                {
                    **path,
                    "fk_table": name_map.get(
                        fk_table,
                        f"{db_name}.{default_schema}.{fk_table}",
                    ),
                    "pk_table": name_map.get(
                        pk_table,
                        f"{db_name}.{default_schema}.{pk_table}",
                    ),
                    "database_name": db_name,
                }
            )

        return RetrievalResult(
            tables=[name_map[table] for table in result.tables],
            table_columns=table_columns,
            table_metadata=metadata,
            semantic_columns=semantic_columns,
            join_paths=join_paths,
            stats=result.stats,
        )

    def retrieve(
        self,
        question: str,
        db_name: str | None = None,
        initial_tables: list[dict[str, Any]] | None = None,
    ) -> RetrievalResult:
        """Retrieve relevant schema for a question.

        Args:
            question: The user question for semantic search.
            db_name: Optional database name filter.
            initial_tables: Optional pre-retrieved tables from schema_hint.
                If provided, skips Milvus table search (reuses these tables).
                Each dict should have: name, score, chinese_name, description.
        """
        stats: dict[str, Any] = {}
        provenance: dict[str, str] = {}

        if initial_tables is not None:
            # Reuse tables from schema_hint (skip Milvus search)
            original_tables = [t["name"] for t in initial_tables]
            table_scores = {t["name"]: t["score"] for t in initial_tables}
            table_metadata = {
                t["name"]: {
                    "chinese_name": t.get("chinese_name"),
                    "description": t.get("description"),
                    "database_name": db_name,
                    "schema_name": t.get("schema_name"),
                }
                for t in initial_tables
            }
            for table in original_tables:
                provenance[table] = "schema_hint"
            stats["milvus_search"] = {
                "count": len(original_tables),
                "tables": original_tables,
                "scores": table_scores,
                "reused_from_hint": True,
            }
        else:
            # Normal Milvus search, isolated to the target database
            search_results = self._milvus.search_tables(
                query=question,
                top_k=self.config.search_top_k,
                db_name=db_name,
            )

            original_tables = [r["table_name"] for r in search_results]
            table_scores = {r["table_name"]: r["score"] for r in search_results}
            table_metadata = {
                r["table_name"]: {
                    "chinese_name": r.get("chinese_name"),
                    "description": r.get("description"),
                    "database_name": r.get("database_name"),
                    "schema_name": r.get("schema_name"),
                }
                for r in search_results
            }
            for table in original_tables:
                provenance[table] = "vector_recall"

            stats["milvus_search"] = {
                "count": len(original_tables),
                "tables": original_tables,
                "scores": table_scores,
            }

        if self.config.expand_fk:
            expanded_tables = self._neo4j.expand_with_related_tables(
                table_names=original_tables,
                max_depth=self.config.expand_max_depth,
                db_name=db_name,
            )

            # Score all FK-expanded tables in ONE batched Milvus call
            # (previously one search per table)
            missing_scores = [t for t in expanded_tables if t not in table_scores]
            if missing_scores:
                score_results = self._milvus.search_tables(
                    query=question,
                    top_k=len(missing_scores),
                    db_name=db_name,
                    table_filter=missing_scores,
                )
                for r in score_results:
                    table_scores[r["table_name"]] = r["score"]
                    table_metadata.setdefault(
                        r["table_name"],
                        {
                            "chinese_name": r.get("chinese_name"),
                            "description": r.get("description"),
                            "database_name": r.get("database_name"),
                            "schema_name": r.get("schema_name"),
                        },
                    )
                for table in missing_scores:
                    table_scores.setdefault(table, 0.0)
                    provenance.setdefault(table, "fk_expansion")

            stats["fk_expansion"] = {
                "before": len(original_tables),
                "after": len(expanded_tables),
                "added": [t for t in expanded_tables if t not in original_tables],
            }
        else:
            expanded_tables = original_tables

        must_keep = set(original_tables)

        context = FilterContext(
            question=question,
            db_name=db_name,
            original_tables=list(original_tables),
            must_keep=must_keep,
            table_scores=table_scores,
            table_metadata=table_metadata,
            table_provenance=provenance,
        )

        filter_result = self._filter_chain.execute(expanded_tables, context)
        final_tables = filter_result.tables
        stats["filters"] = filter_result.stats

        if self.config.bridge_protection_enabled:
            bridge_stats = filter_result.stats.get("chain", {}).get("bridge", {})
            stats["bridge_identification"] = {
                "bridges": bridge_stats.get("bridges_found", []),
            }

        fk_targets = self._neo4j.get_fk_target_tables(
            table_names=final_tables,
            db_name=db_name,
        )
        added_fk_targets = []
        for target in fk_targets:
            if target not in final_tables:
                final_tables.append(target)
                added_fk_targets.append(target)
                provenance.setdefault(target, "fk_target")
        if added_fk_targets:
            stats["fk_target_protection"] = {"added": added_fk_targets}

        table_columns = {}
        if final_tables:
            table_columns = self._neo4j.get_table_columns(
                table_names=final_tables,
                db_name=db_name,
            )

        semantic_columns = []
        if final_tables:
            column_results = self._milvus.search_columns(
                query=question,
                top_k=20,
                db_name=db_name,
                table_filter=final_tables,
            )
            semantic_columns = column_results

        join_paths = []
        if len(final_tables) >= 2:
            join_paths = self._neo4j.find_join_paths_for_tables(
                tables=final_tables,
                max_hops=5,
                db_name=db_name,
            )

        stats["provenance"] = {t: provenance.get(t, "unknown") for t in final_tables}
        stats["final"] = {
            "tables": len(final_tables),
            "table_columns": sum(len(cols) for cols in table_columns.values()),
            "semantic_columns": len(semantic_columns),
            "join_paths": len(join_paths),
        }

        return RetrievalResult(
            tables=final_tables,
            table_columns=table_columns,
            table_metadata=table_metadata,
            semantic_columns=semantic_columns,
            join_paths=join_paths,
            stats=stats,
        )
