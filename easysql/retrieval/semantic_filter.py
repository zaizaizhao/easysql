"""
Semantic Filter

Filters tables based on semantic similarity to the user's question.
Tables with scores below the threshold are removed, unless they are
in the original search results or the core tables whitelist.
"""

from typing import List, Set

from .base import TableFilter, FilterContext, FilterResult


# Empty set - core tables should be configured via environment variables
DEFAULT_CORE_TABLES: Set[str] = set()


class SemanticFilter(TableFilter):
    """
    Filters tables based on semantic similarity scores.
    
    Tables are kept if:
    1. They were in the original Milvus search results
    2. They are core entity tables (configurable whitelist)
    3. Their semantic score is above the threshold
    """
    
    def __init__(
        self,
        threshold: float = 0.4,
        min_tables: int = 3,
        core_tables: Set[str] | None = None,
    ):
        """
        Initialize the semantic filter.
        
        Args:
            threshold: Minimum semantic score to keep a table.
            min_tables: Minimum number of tables to keep, even if below threshold.
            core_tables: Set of table names that are never filtered out.
        """
        self._threshold = threshold
        self._min_tables = min_tables
        self._core_tables = core_tables or DEFAULT_CORE_TABLES
    
    @property
    def name(self) -> str:
        return "semantic"
    
    def filter(
        self,
        tables: List[str],
        context: FilterContext,
    ) -> FilterResult:
        """
        Filter tables by semantic similarity score.
        """
        # If no scores available, return all tables
        if not context.table_scores:
            return FilterResult(
                tables=tables,
                stats={"action": "skipped", "reason": "no scores available"}
            )
        
        original_set = set(context.original_tables)
        
        # Categorize tables
        must_keep = []
        candidates = []
        
        for table in tables:
            # Original tables and core tables are always kept
            if table in original_set or table in self._core_tables:
                must_keep.append(table)
            else:
                score = context.table_scores.get(table, 0)
                candidates.append((table, score))
        
        # Sort candidates by score (descending)
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Keep candidates above threshold
        kept_candidates = [t for t, s in candidates if s >= self._threshold]
        removed = [t for t, s in candidates if s < self._threshold]
        
        # Ensure minimum table count
        result_tables = list(must_keep) + kept_candidates
        
        if len(result_tables) < self._min_tables:
            # Add more tables from removed list
            needed = self._min_tables - len(result_tables)
            # Re-add top-scoring removed tables
            removed_with_scores = [(t, context.table_scores.get(t, 0)) for t in removed]
            removed_with_scores.sort(key=lambda x: x[1], reverse=True)
            for t, _ in removed_with_scores[:needed]:
                result_tables.append(t)
                removed.remove(t)
        
        return FilterResult(
            tables=result_tables,
            stats={
                "action": "semantic_filter",
                "threshold": self._threshold,
                "must_keep": len(must_keep),
                "kept_by_score": len(kept_candidates),
                "removed": removed,
                "before": len(tables),
                "after": len(result_tables),
            }
        )
