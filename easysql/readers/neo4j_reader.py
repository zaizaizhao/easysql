"""
Neo4j Schema Reader - Read-only graph queries for schema retrieval.
"""

from easysql.repositories.neo4j_repository import Neo4jRepository
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


class Neo4jSchemaReader:
    """Read-only Neo4j queries for schema retrieval operations."""

    def __init__(self, repository: Neo4jRepository):
        self._repo = repository

    @property
    def driver(self):
        return self._repo.driver

    @property
    def database(self) -> str:
        return self._repo.database

    def get_table_columns(
        self,
        table_names: list[str],
        db_name: str | None = None,
    ) -> dict[str, list[dict]]:
        """Get complete column information for specified tables."""
        if not table_names:
            return {}

        with self.driver.session(database=self.database) as session:
            if db_name:
                query = """
                UNWIND $tables AS table_name
                MATCH (t:Table {name: table_name, database: $db_name})-[r:HAS_COLUMN]->(c:Column)
                RETURN t.name AS table_name,
                       t.chinese_name AS table_chinese_name,
                       c.name AS name,
                       c.chinese_name AS chinese_name,
                       c.data_type AS data_type,
                       c.base_type AS base_type,
                       c.is_pk AS is_pk,
                       c.is_fk AS is_fk,
                       c.is_nullable AS is_nullable,
                       c.is_indexed AS is_indexed,
                       c.is_unique AS is_unique,
                       c.description AS description,
                       c.ordinal_position AS ordinal_position
                ORDER BY table_name, c.ordinal_position
                """
                result = session.run(query, tables=table_names, db_name=db_name)
            else:
                query = """
                UNWIND $tables AS table_name
                MATCH (t:Table {name: table_name})-[r:HAS_COLUMN]->(c:Column)
                RETURN t.name AS table_name,
                       t.chinese_name AS table_chinese_name,
                       c.name AS name,
                       c.chinese_name AS chinese_name,
                       c.data_type AS data_type,
                       c.base_type AS base_type,
                       c.is_pk AS is_pk,
                       c.is_fk AS is_fk,
                       c.is_nullable AS is_nullable,
                       c.is_indexed AS is_indexed,
                       c.is_unique AS is_unique,
                       c.description AS description,
                       c.ordinal_position AS ordinal_position
                ORDER BY table_name, c.ordinal_position
                """
                result = session.run(query, tables=table_names)

            table_columns: dict[str, list[dict]] = {}

            for record in result:
                table_name = record["table_name"]
                if table_name not in table_columns:
                    table_columns[table_name] = []

                table_columns[table_name].append(
                    {
                        "name": record["name"],
                        "chinese_name": record["chinese_name"],
                        "data_type": record["data_type"],
                        "base_type": record["base_type"],
                        "is_pk": record["is_pk"],
                        "is_fk": record["is_fk"],
                        "is_nullable": record["is_nullable"],
                        "is_indexed": record["is_indexed"],
                        "is_unique": record["is_unique"],
                        "description": record["description"],
                        "ordinal_position": record["ordinal_position"],
                    }
                )

            logger.debug(
                f"Retrieved columns for {len(table_columns)} tables: {list(table_columns.keys())}"
            )

            return table_columns

    def get_table_count(self) -> int:
        """Get total number of tables in Neo4j."""
        with self.driver.session(database=self.database) as session:
            result = session.run("MATCH (t:Table) RETURN count(t) as count")
            record = result.single()
            return record["count"] if record else 0

    def expand_with_related_tables(
        self,
        table_names: list[str],
        max_depth: int = 1,
        db_name: str | None = None,
    ) -> list[str]:
        """Expand table list with FK-related tables."""
        if not table_names:
            return []

        with self.driver.session(database=self.database) as session:
            if db_name:
                query = f"""
                UNWIND $tables AS t
                MATCH (table:Table {{name: t, database: $db_name}})
                MATCH (table)-[:FOREIGN_KEY*1..{max_depth}]-(related:Table {{database: $db_name}})
                RETURN DISTINCT related.name as related_table
                """
                result = session.run(query, tables=table_names, db_name=db_name)
            else:
                query = f"""
                UNWIND $tables AS t
                MATCH (table:Table {{name: t}})
                MATCH (table)-[:FOREIGN_KEY*1..{max_depth}]-(related:Table)
                RETURN DISTINCT related.name as related_table
                """
                result = session.run(query, tables=table_names)

            related = [r["related_table"] for r in result]

            expanded = list(table_names)
            for table in related:
                if table not in expanded:
                    expanded.append(table)

            logger.debug(
                f"Expanded {len(table_names)} tables to {len(expanded)} "
                f"(+{len(expanded) - len(table_names)} related)"
            )
            return expanded

    def find_bridge_tables(
        self,
        high_score_tables: list[str],
        max_hops: int = 3,
        db_name: str | None = None,
    ) -> list[str]:
        """Find bridge tables that connect high-score tables."""
        if len(high_score_tables) < 2:
            return []

        with self.driver.session(database=self.database) as session:
            if db_name:
                query = f"""
                UNWIND $tables AS t1
                UNWIND $tables AS t2
                WITH t1, t2 WHERE t1 < t2

                MATCH (table1:Table {{name: t1, database: $db_name}}),
                      (table2:Table {{name: t2, database: $db_name}})
                MATCH path = shortestPath(
                    (table1)-[:FOREIGN_KEY*1..{max_hops}]-(table2)
                )

                UNWIND nodes(path) AS node
                WITH node.name AS bridge_table
                WHERE NOT bridge_table IN $tables

                RETURN DISTINCT bridge_table
                """
                result = session.run(query, tables=high_score_tables, db_name=db_name)
            else:
                query = f"""
                UNWIND $tables AS t1
                UNWIND $tables AS t2
                WITH t1, t2 WHERE t1 < t2

                MATCH (table1:Table {{name: t1}}), (table2:Table {{name: t2}})
                MATCH path = shortestPath(
                    (table1)-[:FOREIGN_KEY*1..{max_hops}]-(table2)
                )

                UNWIND nodes(path) AS node
                WITH node.name AS bridge_table
                WHERE NOT bridge_table IN $tables

                RETURN DISTINCT bridge_table
                """
                result = session.run(query, tables=high_score_tables)

            bridges = [r["bridge_table"] for r in result]

            if bridges:
                logger.debug(
                    f"Found {len(bridges)} bridge tables for {high_score_tables}: {bridges}"
                )

            return bridges

    def find_join_path(
        self, table1: str, table2: str, max_hops: int = 5, db_name: str | None = None
    ) -> dict[str, list] | None:
        """Find the shortest join path between two tables."""
        with self.driver.session(database=self.database) as session:
            if db_name:
                query = f"""
                MATCH path = shortestPath(
                    (t1:Table {{name: $table1, database: $db_name}})-[:FOREIGN_KEY*1..{max_hops}]-(t2:Table {{name: $table2, database: $db_name}})
                )
                RETURN [node IN nodes(path) | node.name] as tables,
                       [rel IN relationships(path) | {{
                           fk_column: rel.fk_column,
                           pk_column: rel.pk_column
                       }}] as relationships
                """
                result = session.run(query, table1=table1, table2=table2, db_name=db_name)
            else:
                query = f"""
                MATCH path = shortestPath(
                    (t1:Table {{name: $table1}})-[:FOREIGN_KEY*1..{max_hops}]-(t2:Table {{name: $table2}})
                )
                RETURN [node IN nodes(path) | node.name] as tables,
                       [rel IN relationships(path) | {{
                           fk_column: rel.fk_column,
                           pk_column: rel.pk_column
                       }}] as relationships
                """
                result = session.run(query, table1=table1, table2=table2)

            record = result.single()
            if record:
                return {
                    "tables": record["tables"],
                    "relationships": record["relationships"],
                }
            return None

    def find_join_paths_for_tables(
        self, tables: list[str], max_hops: int = 5, db_name: str | None = None
    ) -> list[dict]:
        """Find the unique join edges needed to connect all given tables."""
        with self.driver.session(database=self.database) as session:
            if db_name:
                query = f"""
                UNWIND $tables AS t1
                UNWIND $tables AS t2
                WITH t1, t2 WHERE t1 < t2
                MATCH (table1:Table {{name: t1, database: $db_name}}), (table2:Table {{name: t2, database: $db_name}})
                MATCH path = shortestPath((table1)-[:FOREIGN_KEY*..{max_hops}]-(table2))
                UNWIND relationships(path) AS rel
                WITH DISTINCT
                    startNode(rel).name AS fk_table,
                    endNode(rel).name AS pk_table,
                    rel.fk_column AS fk_column,
                    rel.pk_column AS pk_column
                RETURN fk_table, pk_table, fk_column, pk_column
                """
                result = session.run(query, tables=tables, db_name=db_name)
            else:
                query = f"""
                UNWIND $tables AS t1
                UNWIND $tables AS t2
                WITH t1, t2 WHERE t1 < t2
                MATCH (table1:Table {{name: t1}}), (table2:Table {{name: t2}})
                MATCH path = shortestPath((table1)-[:FOREIGN_KEY*..{max_hops}]-(table2))
                UNWIND relationships(path) AS rel
                WITH DISTINCT
                    startNode(rel).name AS fk_table,
                    endNode(rel).name AS pk_table,
                    rel.fk_column AS fk_column,
                    rel.pk_column AS pk_column
                RETURN fk_table, pk_table, fk_column, pk_column
                """
                result = session.run(query, tables=tables)

            seen = set()
            edges = []
            for record in result:
                edge_key = (record["fk_table"], record["pk_table"], record["fk_column"])
                if edge_key not in seen:
                    seen.add(edge_key)
                    edges.append(dict(record))

            return edges
