"""
PostgreSQL schema extractor for EasySql.

Extracts schema metadata from PostgreSQL databases using
information_schema and pg_catalog.
"""

import re
from typing import Any

import psycopg2
import psycopg2.extras

from easysql.config import DatabaseConfig
from easysql.extractors.base import BaseSchemaExtractor, ExtractorFactory
from easysql.models.schema import (
    ColumnMeta,
    DatabaseType,
    ForeignKeyMeta,
    IndexMeta,
    TableMeta,
)
from easysql.utils.logger import get_logger

logger = get_logger(__name__)


class PostgreSQLSchemaExtractor(BaseSchemaExtractor):
    """
    PostgreSQL database schema extractor.

    Extracts table, column, index, and foreign key metadata
    from PostgreSQL databases using information_schema and pg_catalog.
    """

    def __init__(self, config: DatabaseConfig, schema: str = "public"):
        """
        Initialize PostgreSQL extractor.

        Args:
            config: Database connection configuration
            schema: Schema to extract (default: public)
        """
        super().__init__(config)
        self.schema = schema

    @property
    def db_type(self) -> DatabaseType:
        return DatabaseType.POSTGRESQL

    def connect(self) -> None:
        """Establish connection to PostgreSQL database."""
        try:
            self._connection = psycopg2.connect(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                dbname=self.config.database,
                cursor_factory=psycopg2.extras.RealDictCursor,
            )
            logger.debug(f"Connected to PostgreSQL: {self.config.host}:{self.config.port}")
        except psycopg2.Error as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise ConnectionError(f"PostgreSQL connection failed: {e}") from e

    def disconnect(self) -> None:
        """Close PostgreSQL connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.debug("PostgreSQL connection closed")

    def extract_tables(self) -> list[TableMeta]:
        """Extract all tables with columns and indexes."""
        tables = []

        with self._connection.cursor() as cursor:
            # Get all tables with comments
            cursor.execute(
                """
                SELECT 
                    t.table_name,
                    t.table_type,
                    pg_catalog.obj_description(
                        (quote_ident(t.table_schema) || '.' || quote_ident(t.table_name))::regclass, 
                        'pg_class'
                    ) as table_comment,
                    (SELECT reltuples::bigint 
                     FROM pg_class 
                     WHERE oid = (quote_ident(t.table_schema) || '.' || quote_ident(t.table_name))::regclass
                    ) as row_count
                FROM information_schema.tables t
                WHERE t.table_schema = %s
                  AND t.table_type IN ('BASE TABLE', 'VIEW')
                ORDER BY t.table_name
                """,
                (self.schema,),
            )

            table_rows = cursor.fetchall()
            logger.debug(f"Found {len(table_rows)} tables")

            for row in table_rows:
                table_name = row["table_name"]

                # Extract columns for this table
                columns = self._extract_columns(cursor, table_name)

                # Extract indexes for this table
                indexes = self._extract_indexes(cursor, table_name)

                # Parse Chinese name from comment
                chinese_name, description = self._parse_comment(row["table_comment"])

                # Determine primary key columns
                pk_columns = [col.name for col in columns if col.is_pk]

                table = TableMeta(
                    name=table_name,
                    schema_name=self.schema,
                    chinese_name=chinese_name,
                    description=description or row["table_comment"],
                    row_count=row["row_count"] or 0,
                    is_view=(row["table_type"] == "VIEW"),
                    primary_key=pk_columns,
                    columns=columns,
                    indexes=indexes,
                )
                tables.append(table)

        return tables

    def _extract_columns(self, cursor: Any, table_name: str) -> list[ColumnMeta]:
        """Extract columns for a specific table."""
        cursor.execute(
            """
            SELECT 
                c.column_name,
                c.data_type,
                c.udt_name,
                c.character_maximum_length,
                c.numeric_precision,
                c.numeric_scale,
                c.is_nullable,
                c.column_default,
                c.ordinal_position,
                pg_catalog.col_description(
                    (quote_ident(c.table_schema) || '.' || quote_ident(c.table_name))::regclass,
                    c.ordinal_position
                ) as column_comment,
                CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_pk,
                CASE WHEN uq.column_name IS NOT NULL THEN true ELSE false END as is_unique
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku 
                    ON tc.constraint_name = ku.constraint_name
                    AND tc.table_schema = ku.table_schema
                WHERE tc.table_schema = %s 
                  AND tc.table_name = %s
                  AND tc.constraint_type = 'PRIMARY KEY'
            ) pk ON c.column_name = pk.column_name
            LEFT JOIN (
                SELECT ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku 
                    ON tc.constraint_name = ku.constraint_name
                    AND tc.table_schema = ku.table_schema
                WHERE tc.table_schema = %s 
                  AND tc.table_name = %s
                  AND tc.constraint_type = 'UNIQUE'
            ) uq ON c.column_name = uq.column_name
            WHERE c.table_schema = %s AND c.table_name = %s
            ORDER BY c.ordinal_position
            """,
            (self.schema, table_name, self.schema, table_name, self.schema, table_name),
        )

        columns = []
        for row in cursor.fetchall():
            chinese_name, col_description = self._parse_comment(row["column_comment"])

            # Get full data type with length
            data_type = self._format_data_type(row)

            # Parse enum values if applicable
            enum_values = []
            if row["data_type"] == "USER-DEFINED":
                enum_values = self._get_enum_values(cursor, row["udt_name"])

            column = ColumnMeta(
                name=row["column_name"],
                chinese_name=chinese_name,
                data_type=data_type,
                base_type=row["data_type"],
                length=row["character_maximum_length"],
                precision=row["numeric_precision"],
                scale=row["numeric_scale"],
                is_pk=row["is_pk"],
                is_nullable=(row["is_nullable"] == "YES"),
                is_unique=row["is_unique"],
                default_value=row["column_default"],
                description=col_description or row["column_comment"],
                ordinal_position=row["ordinal_position"],
                enum_values=enum_values,
            )
            columns.append(column)

        # Mark indexed columns
        self._mark_indexed_columns(cursor, table_name, columns)

        return columns

    def _format_data_type(self, row: dict) -> str:
        """Format data type with length/precision."""
        base_type = row["data_type"]

        if row["character_maximum_length"]:
            return f"{base_type}({row['character_maximum_length']})"
        elif row["numeric_precision"]:
            if row["numeric_scale"]:
                return f"{base_type}({row['numeric_precision']},{row['numeric_scale']})"
            return f"{base_type}({row['numeric_precision']})"

        return base_type

    def _mark_indexed_columns(
        self, cursor: Any, table_name: str, columns: list[ColumnMeta]
    ) -> None:
        """Mark columns that have indexes."""
        cursor.execute(
            """
            SELECT a.attname as column_name
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = (quote_ident(%s) || '.' || quote_ident(%s))::regclass
            """,
            (self.schema, table_name),
        )

        indexed_cols = {row["column_name"] for row in cursor.fetchall()}
        for col in columns:
            if col.name in indexed_cols:
                col.is_indexed = True

    def _extract_indexes(self, cursor: Any, table_name: str) -> list[IndexMeta]:
        """Extract indexes for a specific table."""
        cursor.execute(
            """
            SELECT
                i.relname as index_name,
                array_agg(a.attname ORDER BY array_position(ix.indkey, a.attnum)) as columns,
                ix.indisunique as is_unique,
                ix.indisprimary as is_primary,
                am.amname as index_type
            FROM pg_index ix
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_class t ON t.oid = ix.indrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_am am ON am.oid = i.relam
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
            WHERE n.nspname = %s AND t.relname = %s
            GROUP BY i.relname, ix.indisunique, ix.indisprimary, am.amname
            ORDER BY i.relname
            """,
            (self.schema, table_name),
        )

        indexes = []
        for row in cursor.fetchall():
            index = IndexMeta(
                name=row["index_name"],
                columns=row["columns"],
                is_unique=row["is_unique"],
                is_primary=row["is_primary"],
                index_type=row["index_type"].upper(),
            )
            indexes.append(index)

        return indexes

    def extract_foreign_keys(self) -> list[ForeignKeyMeta]:
        """Extract all foreign key relationships."""
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    tc.constraint_name,
                    kcu.table_name as from_table,
                    kcu.column_name as from_column,
                    ccu.table_name as to_table,
                    ccu.column_name as to_column,
                    rc.delete_rule as on_delete,
                    rc.update_rule as on_update
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                    AND ccu.table_schema = tc.table_schema
                JOIN information_schema.referential_constraints rc
                    ON rc.constraint_name = tc.constraint_name
                    AND rc.constraint_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = %s
                ORDER BY tc.constraint_name
                """,
                (self.schema,),
            )

            foreign_keys = []
            for row in cursor.fetchall():
                fk = ForeignKeyMeta(
                    constraint_name=row["constraint_name"],
                    from_table=row["from_table"],
                    from_column=row["from_column"],
                    to_table=row["to_table"],
                    to_column=row["to_column"],
                    on_delete=row["on_delete"] or "NO ACTION",
                    on_update=row["on_update"] or "NO ACTION",
                )
                foreign_keys.append(fk)

            return foreign_keys

    def _get_enum_values(self, cursor: Any, enum_name: str) -> list[str]:
        """Get enum values for a user-defined enum type."""
        cursor.execute(
            """
            SELECT enumlabel
            FROM pg_enum
            JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
            WHERE pg_type.typname = %s
            ORDER BY enumsortorder
            """,
            (enum_name,),
        )
        return [row["enumlabel"] for row in cursor.fetchall()]

    def _parse_comment(self, comment: str | None) -> tuple[str | None, str | None]:
        """
        Parse Chinese name and description from comment.

        Handles formats like:
        - "中文名"
        - "中文名-描述"
        - "中文名: 描述"
        """
        if not comment:
            return None, None

        comment = comment.strip()

        # Try to extract Chinese name (first continuous Chinese characters)
        match = re.match(r"^([\u4e00-\u9fa5]+)", comment)
        chinese_name = match.group(1) if match else None

        # If the comment is longer, the rest is description
        if chinese_name and len(comment) > len(chinese_name):
            description = comment
        else:
            description = None

        return chinese_name, description


# Register the extractor with the factory
ExtractorFactory.register("postgresql", PostgreSQLSchemaExtractor)
