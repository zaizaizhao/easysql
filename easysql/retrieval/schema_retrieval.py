"""
Schema Retrieval Service

The main service that orchestrates schema retrieval for Text2SQL.
Combines Milvus semantic search, Neo4j FK expansion, and configurable filters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .base import FilterChain, FilterContext, NoOpFilter
from .bridge_filter import BridgeFilter
from .llm_filter import LLMFilter
from .semantic_filter import SemanticFilter

if TYPE_CHECKING:
    from easysql.config import Settings
    from easysql.readers.milvus_reader import MilvusSchemaReader
    from easysql.readers.neo4j_reader import Neo4jSchemaReader


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

    llm_api_key: str | None = None

    llm_api_base: str | None = None


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
    ):
        self._milvus = milvus_reader
        self._neo4j = neo4j_reader
        self.config = config or RetrievalConfig()

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

        if self.config.llm_filter_enabled and self.config.llm_api_key:
            chain.add(
                LLMFilter(
                    api_key=self.config.llm_api_key,
                    api_base=self.config.llm_api_base,
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
            bridge_max_hops=settings.bridge_max_hops,
            core_tables=settings.core_tables_list,
            llm_filter_enabled=settings.llm_filter_enabled,
            llm_filter_max_tables=settings.llm_filter_max_tables,
            llm_filter_model=settings.llm_filter_model,
            llm_api_key=settings.llm_api_key,
            llm_api_base=settings.llm_api_base,
        )

        return cls(milvus_reader=milvus_reader, neo4j_reader=neo4j_reader, config=config)

    def retrieve(
        self,
        question: str,
        db_name: str | None = None,
    ) -> RetrievalResult:
        """Retrieve relevant schema for a question."""
        stats: dict[str, Any] = {}

        search_results = self._milvus.search_tables(
            query=question,
            top_k=self.config.search_top_k,
        )

        original_tables = [r["table_name"] for r in search_results]
        table_scores = {r["table_name"]: r["score"] for r in search_results}
        table_metadata = {
            r["table_name"]: {
                "chinese_name": r.get("chinese_name"),
                "description": r.get("description"),
                "database_name": r.get("database_name"),
            }
            for r in search_results
        }

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

            for table in expanded_tables:
                if table not in table_scores:
                    result = self._milvus.search_tables(
                        query=question,
                        top_k=1,
                        filter_expr=f'table_name == "{table}"',
                    )
                    if result:
                        table_scores[table] = result[0]["score"]
                    else:
                        table_scores[table] = 0.0

            stats["fk_expansion"] = {
                "before": len(original_tables),
                "after": len(expanded_tables),
                "added": [t for t in expanded_tables if t not in original_tables],
            }
        else:
            expanded_tables = original_tables

        bridge_tables = []
        if self.config.bridge_protection_enabled and len(original_tables) >= 2:
            bridge_tables = self._neo4j.find_bridge_tables(
                high_score_tables=original_tables,
                max_hops=self.config.bridge_max_hops,
                db_name=db_name,
            )
            stats["bridge_identification"] = {
                "bridges": bridge_tables,
            }

        must_keep_tables = list(original_tables)
        for bridge in bridge_tables:
            if bridge not in must_keep_tables:
                must_keep_tables.append(bridge)
            if bridge not in expanded_tables:
                expanded_tables.append(bridge)

        context = FilterContext(
            question=question,
            db_name=db_name,
            original_tables=must_keep_tables,
            table_scores=table_scores,
            table_metadata=table_metadata,
        )

        filter_result = self._filter_chain.execute(expanded_tables, context)
        final_tables = filter_result.tables
        stats["filters"] = filter_result.stats

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