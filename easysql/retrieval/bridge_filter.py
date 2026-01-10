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

from typing import TYPE_CHECKING

from .base import FilterContext, FilterResult, TableFilter

if TYPE_CHECKING:
    from easysql.readers.neo4j_reader import Neo4jSchemaReader


class BridgeFilter(TableFilter):
    """
    Protects bridge tables and direct FK neighbors.

    This filter doesn't remove tables; it only adds back tables
    that are needed to connect the existing tables or are directly
    connected via FK relationships.
    """

    def __init__(
        self,
        neo4j_reader: "Neo4jSchemaReader",
        max_hops: int = 3,
        include_direct_neighbors: bool = True,
        protected_tables: set[str] | None = None,
    ):
        self._neo4j = neo4j_reader
        self._max_hops = max_hops
        self._include_direct_neighbors = include_direct_neighbors
        self._protected_tables = protected_tables or set()

    @property
    def name(self) -> str:
        return "bridge"

    def filter(
        self,
        tables: list[str],
        context: FilterContext,
    ) -> FilterResult:
        """Find and add bridge tables and direct FK neighbors."""
        if len(tables) < 2:
            return FilterResult(
                tables=tables, stats={"action": "skipped", "reason": "less than 2 tables"}
            )

        added = []
        result_tables = list(tables)

        bridge_tables = self._neo4j.find_bridge_tables(
            high_score_tables=tables,
            max_hops=self._max_hops,
            db_name=context.db_name,
        )

        for bridge in bridge_tables:
            if bridge not in result_tables:
                result_tables.append(bridge)
                added.append(bridge)
                if bridge not in context.original_tables:
                    context.original_tables.append(bridge)

        direct_neighbors = []
        if self._include_direct_neighbors:
            all_expanded = set()

            for table in tables:
                neighbors = self._neo4j.expand_with_related_tables(
                    table_names=[table],
                    max_depth=1,
                    db_name=context.db_name,
                )
                all_expanded.update(neighbors)

            for table in all_expanded:
                if table in self._protected_tables and table not in result_tables:
                    result_tables.append(table)
                    direct_neighbors.append(table)
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
            },
        )
