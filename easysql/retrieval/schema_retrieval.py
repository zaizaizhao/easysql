"""
Schema Retrieval Service

The main service that orchestrates schema retrieval for Text2SQL.
Combines Milvus semantic search, Neo4j FK expansion, and configurable filters.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from .base import FilterContext, FilterResult, FilterChain, NoOpFilter
from .semantic_filter import SemanticFilter
from .bridge_filter import BridgeFilter
from .llm_filter import LLMFilter

if TYPE_CHECKING:
    from easysql.writers.milvus_writer import MilvusVectorWriter
    from easysql.writers.neo4j_writer import Neo4jSchemaWriter


@dataclass
class RetrievalResult:
    """Result of schema retrieval."""
    
    tables: List[str]
    """Final list of relevant table names."""
    
    columns: List[Dict[str, Any]] = field(default_factory=list)
    """Relevant columns from the tables."""
    
    join_paths: List[Dict[str, str]] = field(default_factory=list)
    """FK join paths between tables."""
    
    stats: Dict[str, Any] = field(default_factory=dict)
    """Statistics about the retrieval process."""


@dataclass
class RetrievalConfig:
    """Configuration for schema retrieval."""
    
    # Milvus search
    search_top_k: int = 5
    """Number of tables to retrieve from Milvus."""
    
    # FK expansion
    expand_fk: bool = True
    """Whether to expand tables via FK relationships."""
    
    expand_max_depth: int = 1
    """Maximum FK depth for expansion."""
    
    # Semantic filter
    semantic_filter_enabled: bool = True
    """Whether to apply semantic filtering."""
    
    semantic_threshold: float = 0.4
    """Minimum score for semantic filter."""
    
    semantic_min_tables: int = 3
    """Minimum tables to keep after semantic filter."""
    
    # Bridge protection
    bridge_protection_enabled: bool = True
    """Whether to protect bridge tables."""
    
    bridge_max_hops: int = 3
    """Maximum hops for bridge table detection."""
    
    # Core tables
    core_tables: Optional[List[str]] = None
    """Tables that should never be filtered out."""
    
    # LLM filter
    llm_filter_enabled: bool = False
    """Whether to use LLM for table filtering."""
    
    llm_filter_max_tables: int = 8
    """Maximum tables after LLM filtering."""
    
    llm_filter_model: str = "deepseek-chat"
    """LLM model name."""
    
    llm_api_key: Optional[str] = None
    """LLM API key."""
    
    llm_api_base: Optional[str] = None
    """LLM API base URL."""


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
        milvus: "MilvusVectorWriter",
        neo4j: "Neo4jSchemaWriter",
        config: Optional[RetrievalConfig] = None,
    ):
        """
        Initialize the service.
        
        Args:
            milvus: Milvus writer for semantic search.
            neo4j: Neo4j writer for graph queries.
            config: Retrieval configuration.
        """
        self.milvus = milvus
        self.neo4j = neo4j
        self.config = config or RetrievalConfig()
        
        # Build filter chain based on config
        self._filter_chain = self._build_filter_chain()
    
    def _build_filter_chain(self) -> FilterChain:
        """Build the filter chain based on config."""
        chain = FilterChain()
        
        if self.config.semantic_filter_enabled:
            core_tables = set(self.config.core_tables) if self.config.core_tables else None
            chain.add(SemanticFilter(
                threshold=self.config.semantic_threshold,
                min_tables=self.config.semantic_min_tables,
                core_tables=core_tables,
            ))
        
        if self.config.bridge_protection_enabled:
            # Protected tables are core tables that should be recovered if they
            # are direct FK neighbors of high-score tables
            protected = set(self.config.core_tables) if self.config.core_tables else set()
            chain.add(BridgeFilter(
                neo4j_writer=self.neo4j,
                max_hops=self.config.bridge_max_hops,
                include_direct_neighbors=True,
                protected_tables=protected,
            ))
        
        # LLM filter (last in chain)
        if self.config.llm_filter_enabled and self.config.llm_api_key:
            chain.add(LLMFilter(
                api_key=self.config.llm_api_key,
                api_base=self.config.llm_api_base,
                model=self.config.llm_filter_model,
                max_tables=self.config.llm_filter_max_tables,
            ))
        
        # If no filters, add NoOp
        if not chain.filters:
            chain.add(NoOpFilter())
        
        return chain
    
    @classmethod
    def from_settings(
        cls,
        milvus: "MilvusVectorWriter",
        neo4j: "Neo4jSchemaWriter",
        settings: "Settings" = None,
    ) -> "SchemaRetrievalService":
        """
        Create service from Settings (environment variables).
        
        Args:
            milvus: Milvus writer instance.
            neo4j: Neo4j writer instance.
            settings: Settings instance (uses get_settings() if None).
        
        Returns:
            Configured SchemaRetrievalService.
        """
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
        
        return cls(milvus=milvus, neo4j=neo4j, config=config)
    
    def retrieve(
        self,
        question: str,
        db_name: Optional[str] = None,
    ) -> RetrievalResult:
        """
        Retrieve relevant schema for a question.
        
        Args:
            question: User's natural language question.
            db_name: Optional database name for isolation.
        
        Returns:
            RetrievalResult with tables, columns, join paths, and stats.
        """
        stats: Dict[str, Any] = {}
        
        # Step 1: Milvus semantic search
        search_results = self.milvus.search_tables(
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
        
        # Step 2: FK expansion
        if self.config.expand_fk:
            expanded_tables = self.neo4j.expand_with_related_tables(
                table_names=original_tables,
                max_depth=self.config.expand_max_depth,
                db_name=db_name,
            )
            
            # Get scores for expanded tables
            for table in expanded_tables:
                if table not in table_scores:
                    # Query Milvus for the score
                    result = self.milvus.search_tables(
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
        
        # Step 3: Identify bridge tables BEFORE semantic filtering
        # Bridge tables connect high-score tables and should be protected
        bridge_tables = []
        if self.config.bridge_protection_enabled and len(original_tables) >= 2:
            bridge_tables = self.neo4j.find_bridge_tables(
                high_score_tables=original_tables,
                max_hops=self.config.bridge_max_hops,
                db_name=db_name,
            )
            stats["bridge_identification"] = {
                "bridges": bridge_tables,
            }
        
        # Create must-keep list: original tables + bridge tables
        must_keep_tables = list(original_tables)
        for bridge in bridge_tables:
            if bridge not in must_keep_tables:
                must_keep_tables.append(bridge)
        
        # Step 4: Apply filter chain
        context = FilterContext(
            question=question,
            db_name=db_name,
            original_tables=must_keep_tables,  # Now includes bridge tables
            table_scores=table_scores,
            table_metadata=table_metadata,
        )
        
        filter_result = self._filter_chain.execute(expanded_tables, context)
        final_tables = filter_result.tables
        stats["filters"] = filter_result.stats
        
        # Step 5: Get columns for final tables
        columns = []
        if final_tables:
            column_results = self.milvus.search_columns(
                query=question,
                top_k=20,
                table_filter=final_tables,
            )
            columns = column_results
        
        # Step 6: Get JOIN paths
        join_paths = []
        if len(final_tables) >= 2:
            join_paths = self.neo4j.find_join_paths_for_tables(
                tables=final_tables,
                max_hops=5,
                db_name=db_name,
            )
        
        stats["final"] = {
            "tables": len(final_tables),
            "columns": len(columns),
            "join_paths": len(join_paths),
        }
        
        return RetrievalResult(
            tables=final_tables,
            columns=columns,
            join_paths=join_paths,
            stats=stats,
        )
