"""
Bridge Table Filter

Protects "bridge tables" that connect high-score tables together.
Even if a table has low semantic similarity, it should be kept if it's
on the shortest path between two tables that ARE relevant.

Also optionally protects direct FK neighbors of high-score tables.

Example:
    High score tables: [patient, prescription]
    Bridge table: outpatient_visit (connects patient to prescription via FK)
    Direct FK neighbor: employee (directly connected to prescription via doctor_id)
"""

from typing import List, Set, TYPE_CHECKING

from .base import TableFilter, FilterContext, FilterResult

if TYPE_CHECKING:
    from easysql.writers.neo4j_writer import Neo4jSchemaWriter


class BridgeFilter(TableFilter):
    """
    Protects bridge tables and direct FK neighbors.
    
    This filter doesn't remove tables; it only adds back tables
    that are needed to connect the existing tables or are directly
    connected via FK relationships.
    """
    
    def __init__(
        self,
        neo4j_writer: "Neo4jSchemaWriter",
        max_hops: int = 3,
        include_direct_neighbors: bool = True,
        protected_tables: Set[str] | None = None,
    ):
        """
        Initialize the bridge filter.
        
        Args:
            neo4j_writer: Neo4j writer instance for graph queries.
            max_hops: Maximum FK hops to consider for bridges.
            include_direct_neighbors: Also protect tables with direct FK to high-score tables.
            protected_tables: Set of table names that should always be protected if found.
        """
        self._neo4j = neo4j_writer
        self._max_hops = max_hops
        self._include_direct_neighbors = include_direct_neighbors
        self._protected_tables = protected_tables or set()
    
    @property
    def name(self) -> str:
        return "bridge"
    
    def filter(
        self,
        tables: List[str],
        context: FilterContext,
    ) -> FilterResult:
        """
        Find and add bridge tables and direct FK neighbors.
        
        This filter only ADDS tables, never removes them.
        """
        if len(tables) < 2:
            return FilterResult(
                tables=tables,
                stats={"action": "skipped", "reason": "less than 2 tables"}
            )
        
        added = []
        result_tables = list(tables)
        
        # 1. Find bridge tables (intermediate tables on shortest path)
        bridge_tables = self._neo4j.find_bridge_tables(
            high_score_tables=tables,
            max_hops=self._max_hops,
            db_name=context.db_name,
        )
        
        for bridge in bridge_tables:
            if bridge not in result_tables:
                result_tables.append(bridge)
                added.append(bridge)
                # IMPORTANT: Also add to context.original_tables so subsequent
                # filters (like LLMFilter) will protect these tables
                if bridge not in context.original_tables:
                    context.original_tables.append(bridge)
        
        # 2. Find direct FK neighbors (tables directly connected via FK)
        direct_neighbors = []
        if self._include_direct_neighbors:
            # Get all tables that were removed by semantic filter
            # These are candidates for recovery if they have direct FK to kept tables
            all_expanded = set()
            
            # Expand each kept table to find direct FK neighbors
            for table in tables:
                neighbors = self._neo4j.expand_with_related_tables(
                    table_names=[table],
                    max_depth=1,  # Only direct neighbors
                    db_name=context.db_name,
                )
                all_expanded.update(neighbors)
            
            # Check if any protected tables are in the expanded set
            for table in all_expanded:
                if table in self._protected_tables and table not in result_tables:
                    result_tables.append(table)
                    direct_neighbors.append(table)
                    # Also protect in context
                    if table not in context.original_tables:
                        context.original_tables.append(table)
        
        return FilterResult(
            tables=result_tables,
            stats={
                "action": "add_bridges",
                "bridges_found": bridge_tables,
                "bridges_added": [t for t in added if t not in direct_neighbors],
                "direct_neighbors_added": direct_neighbors,
                "before": len(tables),
                "after": len(result_tables),
            }
        )

