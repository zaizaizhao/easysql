"""
Neo4j schema writer for EasySql.

Writes database schema metadata to Neo4j graph database,
creating nodes for databases, tables, columns and their relationships.
"""

from typing import Any

from easysql.models.schema import DatabaseMeta, ForeignKeyMeta, TableMeta
from easysql.repositories.neo4j_repository import Neo4jRepository
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


class Neo4jSchemaWriter:
    """
    Neo4j graph database writer for schema metadata.

    Creates a graph structure representing database schema:
    - Database nodes connected to Table nodes
    - Table nodes connected to Column nodes
    - Foreign key relationships between tables
    """

    def __init__(self, repository: Neo4jRepository):
        self._repo = repository

    @property
    def driver(self):
        return self._repo.driver

    @property
    def database(self) -> str:
        return self._repo.database

    def write_database(self, db_meta: DatabaseMeta) -> dict[str, int]:
        """Write complete database metadata to Neo4j."""
        logger.info(f"Writing database '{db_meta.name}' to Neo4j")

        stats = {"databases": 0, "tables": 0, "columns": 0, "foreign_keys": 0}

        with self.driver.session(database=self.database) as session:
            session.execute_write(self._create_database_node, db_meta)
            stats["databases"] = 1

            for table in db_meta.tables:
                session.execute_write(self._create_table_with_columns, db_meta.name, table)
                stats["tables"] += 1
                stats["columns"] += len(table.columns)

            for fk in db_meta.foreign_keys:
                session.execute_write(self._create_foreign_key_relationship, db_meta.name, fk)
                stats["foreign_keys"] += 1

        logger.info(
            f"Neo4j write complete: {stats['tables']} tables, "
            f"{stats['columns']} columns, {stats['foreign_keys']} FKs"
        )
        return stats

    @staticmethod
    def _create_database_node(tx: Any, db_meta: DatabaseMeta) -> None:
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
        table_id = table.get_id(db_name)

        tx.run(
            """
            MATCH (db:Database {name: $db_name})
            MERGE (t:Table {id: $table_id})
            SET t.name = $name,
                t.database = $db_name,
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

        for col in table.columns:
            col_id = col.get_id(db_name, table.schema_name, table.name)
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
    def _create_foreign_key_relationship(tx: Any, db_name: str, fk: ForeignKeyMeta) -> None:
        from_table_id = fk.get_from_table_id(db_name)
        to_table_id = fk.get_to_table_id(db_name)

        tx.run(
            """
            MATCH (t1:Table {id: $from_table_id})
            MATCH (t2:Table {id: $to_table_id})
            MERGE (t1)-[r:FOREIGN_KEY {constraint_name: $constraint_name}]->(t2)
            SET r.fk_column = $fk_column,
                r.pk_column = $pk_column,
                r.from_schema = $from_schema,
                r.to_schema = $to_schema,
                r.on_delete = $on_delete,
                r.on_update = $on_update,
                r.updated_at = datetime()
            """,
            from_table_id=from_table_id,
            to_table_id=to_table_id,
            constraint_name=fk.constraint_name,
            fk_column=fk.from_column,
            pk_column=fk.to_column,
            from_schema=fk.from_schema,
            to_schema=fk.to_schema,
            on_delete=fk.on_delete,
            on_update=fk.on_update,
        )

    def clear_database(self, db_name: str) -> int:
        """Remove all nodes and relationships for a specific database."""
        logger.warning(f"Clearing Neo4j data for database: {db_name}")

        with self.driver.session(database=self.database) as session:
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

    def __enter__(self) -> "Neo4jSchemaWriter":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass
