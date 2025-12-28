"""
Neo4j schema writer for EasySql.

Writes database schema metadata to Neo4j graph database,
creating nodes for databases, tables, columns and their relationships.
"""

from typing import Any

from neo4j import GraphDatabase, Driver

from easysql.models.schema import DatabaseMeta, ForeignKeyMeta, TableMeta
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


class Neo4jSchemaWriter:
    """
    Neo4j graph database writer for schema metadata.

    Creates a graph structure representing database schema:
    - Database nodes connected to Table nodes
    - Table nodes connected to Column nodes
    - Foreign key relationships between tables

    Usage:
        writer = Neo4jSchemaWriter(uri, user, password)
        writer.write_database(db_meta)
        writer.close()
    """

    def __init__(self, uri: str, user: str, password: str):
        """
        Initialize Neo4j writer.

        Args:
            uri: Neo4j connection URI (e.g., bolt://localhost:7687)
            user: Neo4j username
            password: Neo4j password
        """
        self.uri = uri
        self.user = user
        self.password = password
        self._driver: Driver | None = None

    def connect(self) -> None:
        """Establish connection to Neo4j."""
        try:
            self._driver = GraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )
            # Verify connectivity
            self._driver.verify_connectivity()
            logger.info(f"Connected to Neo4j: {self.uri}")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise ConnectionError(f"Neo4j connection failed: {e}") from e

    def close(self) -> None:
        """Close Neo4j connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.debug("Neo4j connection closed")

    @property
    def driver(self) -> Driver:
        """Get the Neo4j driver, connecting if necessary."""
        if not self._driver:
            self.connect()
        return self._driver

    def write_database(self, db_meta: DatabaseMeta) -> dict[str, int]:
        """
        Write complete database metadata to Neo4j.

        Args:
            db_meta: Database metadata to write

        Returns:
            Statistics dictionary with counts of created nodes/relationships
        """
        logger.info(f"Writing database '{db_meta.name}' to Neo4j")

        stats = {"databases": 0, "tables": 0, "columns": 0, "foreign_keys": 0}

        with self.driver.session() as session:
            # Create database node
            session.execute_write(self._create_database_node, db_meta)
            stats["databases"] = 1

            # Create tables with columns
            for table in db_meta.tables:
                session.execute_write(
                    self._create_table_with_columns, db_meta.name, table
                )
                stats["tables"] += 1
                stats["columns"] += len(table.columns)

            # Create foreign key relationships
            for fk in db_meta.foreign_keys:
                session.execute_write(
                    self._create_foreign_key_relationship, db_meta.name, fk
                )
                stats["foreign_keys"] += 1

        logger.info(
            f"Neo4j write complete: {stats['tables']} tables, "
            f"{stats['columns']} columns, {stats['foreign_keys']} FKs"
        )
        return stats

    @staticmethod
    def _create_database_node(tx: Any, db_meta: DatabaseMeta) -> None:
        """Create or update a Database node."""
        tx.run(
            """
            MERGE (db:Database {name: $name})
            SET db.db_type = $db_type,
                db.host = $host,
                db.port = $port,
                db.system_type = $system_type,
                db.description = $description,
                db.updated_at = datetime()
            """,
            name=db_meta.name,
            db_type=db_meta.db_type.value,
            host=db_meta.host,
            port=db_meta.port,
            system_type=db_meta.system_type,
            description=db_meta.description,
        )

    @staticmethod
    def _create_table_with_columns(tx: Any, db_name: str, table: TableMeta) -> None:
        """Create a Table node with its Column nodes."""
        table_id = table.get_id(db_name)

        # Create table node and link to database
        tx.run(
            """
            MATCH (db:Database {name: $db_name})
            MERGE (t:Table {id: $table_id})
            SET t.name = $name,
                t.schema_name = $schema_name,
                t.chinese_name = $chinese_name,
                t.description = $description,
                t.business_domain = $business_domain,
                t.row_count = $row_count,
                t.is_archive = $is_archive,
                t.is_view = $is_view,
                t.primary_key = $primary_key,
                t.updated_at = datetime()
            MERGE (db)-[:HAS_TABLE]->(t)
            """,
            db_name=db_name,
            table_id=table_id,
            name=table.name,
            schema_name=table.schema_name,
            chinese_name=table.chinese_name,
            description=table.description,
            business_domain=table.business_domain,
            row_count=table.row_count,
            is_archive=table.is_archive,
            is_view=table.is_view,
            primary_key=table.primary_key,
        )

        # Create column nodes
        for col in table.columns:
            col_id = col.get_id(db_name, table.name)
            tx.run(
                """
                MATCH (t:Table {id: $table_id})
                MERGE (c:Column {id: $col_id})
                SET c.name = $name,
                    c.chinese_name = $chinese_name,
                    c.data_type = $data_type,
                    c.base_type = $base_type,
                    c.is_pk = $is_pk,
                    c.is_fk = $is_fk,
                    c.is_nullable = $is_nullable,
                    c.is_indexed = $is_indexed,
                    c.is_unique = $is_unique,
                    c.description = $description,
                    c.ordinal_position = $ordinal_position,
                    c.updated_at = datetime()
                MERGE (t)-[:HAS_COLUMN {ordinal_position: $ordinal_position}]->(c)
                """,
                table_id=table_id,
                col_id=col_id,
                name=col.name,
                chinese_name=col.chinese_name,
                data_type=col.data_type,
                base_type=col.base_type,
                is_pk=col.is_pk,
                is_fk=col.is_fk,
                is_nullable=col.is_nullable,
                is_indexed=col.is_indexed,
                is_unique=col.is_unique,
                description=col.description,
                ordinal_position=col.ordinal_position,
            )

    @staticmethod
    def _create_foreign_key_relationship(
        tx: Any, db_name: str, fk: ForeignKeyMeta
    ) -> None:
        """Create a FOREIGN_KEY relationship between tables."""
        tx.run(
            """
            MATCH (t1:Table) WHERE t1.name = $from_table AND t1.id STARTS WITH $db_prefix
            MATCH (t2:Table) WHERE t2.name = $to_table AND t2.id STARTS WITH $db_prefix
            MERGE (t1)-[r:FOREIGN_KEY {constraint_name: $constraint_name}]->(t2)
            SET r.fk_column = $fk_column,
                r.pk_column = $pk_column,
                r.on_delete = $on_delete,
                r.on_update = $on_update,
                r.updated_at = datetime()
            """,
            db_prefix=f"{db_name}.",
            from_table=fk.from_table,
            to_table=fk.to_table,
            constraint_name=fk.constraint_name,
            fk_column=fk.from_column,
            pk_column=fk.to_column,
            on_delete=fk.on_delete,
            on_update=fk.on_update,
        )

    def clear_database(self, db_name: str) -> int:
        """
        Remove all nodes and relationships for a specific database.

        Args:
            db_name: Name of the database to clear

        Returns:
            Number of nodes deleted
        """
        logger.warning(f"Clearing Neo4j data for database: {db_name}")

        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (db:Database {name: $db_name})-[:HAS_TABLE]->(t:Table)-[:HAS_COLUMN]->(c:Column)
                DETACH DELETE c
                WITH count(*) as deleted_cols
                MATCH (db:Database {name: $db_name})-[:HAS_TABLE]->(t:Table)
                DETACH DELETE t
                WITH count(*) as deleted_tables
                MATCH (db:Database {name: $db_name})
                DETACH DELETE db
                RETURN deleted_tables + 1 as total_deleted
                """,
                db_name=db_name,
            )
            record = result.single()
            deleted = record["total_deleted"] if record else 0
            logger.info(f"Cleared {deleted} nodes for database: {db_name}")
            return deleted

    def get_table_count(self) -> int:
        """Get total number of tables in Neo4j."""
        with self.driver.session() as session:
            result = session.run("MATCH (t:Table) RETURN count(t) as count")
            record = result.single()
            return record["count"] if record else 0

    def find_join_path(
        self, table1: str, table2: str, max_hops: int = 5
    ) -> list[dict] | None:
        """
        Find the shortest join path between two tables.

        Args:
            table1: First table name
            table2: Second table name
            max_hops: Maximum number of hops

        Returns:
            List of path nodes/relationships or None if no path found
        """
        with self.driver.session() as session:
            result = session.run(
                f"""
                MATCH path = shortestPath(
                    (t1:Table {{name: $table1}})-[:FOREIGN_KEY*1..{max_hops}]-(t2:Table {{name: $table2}})
                )
                RETURN [node IN nodes(path) | node.name] as tables,
                       [rel IN relationships(path) | {{
                           fk_column: rel.fk_column, 
                           pk_column: rel.pk_column
                       }}] as relationships
                """,
                table1=table1,
                table2=table2,
            )
            record = result.single()
            if record:
                return {
                    "tables": record["tables"],
                    "relationships": record["relationships"],
                }
            return None

    def __enter__(self) -> "Neo4jSchemaWriter":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
