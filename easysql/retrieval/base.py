"""
Table Filter Base Classes

Provides abstract base class for table filtering strategies used in schema retrieval.
Filters can be combined in a chain to progressively refine the table list.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class FilterContext:
    """Context information passed to filters during execution."""
    
    question: str
    """The user's natural language question."""
    
    db_name: Optional[str] = None
    """Database name for isolation (optional)."""
    
    original_tables: List[str] = field(default_factory=list)
    """Tables from original Milvus search (should not be filtered out)."""
    
    table_scores: Dict[str, float] = field(default_factory=dict)
    """Semantic similarity scores for each table."""
    
    table_metadata: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    """Additional metadata for tables (chinese_name, description, etc.)."""
    
    join_paths: List[Dict[str, str]] = field(default_factory=list)
    """FK join paths between tables."""


@dataclass
class FilterResult:
    """Result of a filter operation."""
    
    tables: List[str]
    """Filtered list of table names."""
    
    stats: Dict[str, Any] = field(default_factory=dict)
    """Statistics about the filtering operation."""


class TableFilter(ABC):
    """
    Abstract base class for table filters.
    
    Filters are used to refine the list of tables retrieved from Milvus
    before passing to the LLM for SQL generation.
    
    Filters can be chained together:
        expanded_tables → SemanticFilter → BridgeFilter → LLMFilter → final_tables
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the filter name for logging and debugging."""
        pass
    
    @abstractmethod
    def filter(
        self,
        tables: List[str],
        context: FilterContext,
    ) -> FilterResult:
        """
        Filter the table list.
        
        Args:
            tables: List of table names to filter.
            context: Context information including the question and metadata.
        
        Returns:
            FilterResult containing filtered tables and stats.
        """
        pass


class NoOpFilter(TableFilter):
    """
    A pass-through filter that doesn't modify the table list.
    
    Used as the default when no filtering is configured.
    """
    
    @property
    def name(self) -> str:
        return "noop"
    
    def filter(
        self,
        tables: List[str],
        context: FilterContext,
    ) -> FilterResult:
        return FilterResult(
            tables=tables,
            stats={"action": "passthrough", "count": len(tables)}
        )


class FilterChain:
    """
    Executes multiple filters in sequence.
    
    Each filter's output becomes the input for the next filter.
    """
    
    def __init__(self, filters: List[TableFilter] | None = None):
        self.filters = filters or []
    
    def add(self, filter_: TableFilter) -> "FilterChain":
        """Add a filter to the chain."""
        self.filters.append(filter_)
        return self
    
    def execute(
        self,
        tables: List[str],
        context: FilterContext,
    ) -> FilterResult:
        """
        Execute all filters in sequence.
        
        Args:
            tables: Initial list of tables.
            context: Filter context.
        
        Returns:
            Final FilterResult after all filters.
        """
        current_tables = tables
        all_stats = {}
        
        for filter_ in self.filters:
            result = filter_.filter(current_tables, context)
            current_tables = result.tables
            all_stats[filter_.name] = result.stats
        
        return FilterResult(
            tables=current_tables,
            stats={"chain": all_stats, "final_count": len(current_tables)}
        )
