"""
MySQL schema extractor for EasySql.

Extracts schema metadata from MySQL databases using information_schema.
"""

import re
from typing import Any

import pymysql

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


class MySQLSchemaExtractor(BaseSchemaExtractor):
    """
    MySQL database schema extractor.

    Extracts table, column, index, and foreign key metadata
    from MySQL databases using information_schema queries.
    """

    @property
    def db_type(self) -> DatabaseType:
        return DatabaseType.MYSQL

    def connect(self) -> None:
        """Establish connection to MySQL database."""
        try:
            self._connection = pymysql.connect(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                database=self.config.database,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
            )
            logger.debug(f"Connected to MySQL: {self.config.host}:{self.config.port}")
        except pymysql.Error as e:
            logger.error(f"Failed to connect to MySQL: {e}")
            raise ConnectionError(f"MySQL connection failed: {e}") from e

    def disconnect(self) -> None:
        """Close MySQL connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
            logger.debug("MySQL connection closed")

    def extract_tables(self) -> list[TableMeta]:
        """Extract all tables with columns and indexes."""
        tables = []

        with self._connection.cursor() as cursor:
            # Get all tables
            cursor.execute(
                """
                SELECT 
                    TABLE_NAME,
                    TABLE_COMMENT,
                    TABLE_ROWS,
                    TABLE_TYPE
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = %s
                  AND TABLE_TYPE IN ('BASE TABLE', 'VIEW')
                ORDER BY TABLE_NAME
                """,
                (self.config.database,),
            )

            table_rows = cursor.fetchall()
            logger.debug(f"Found {len(table_rows)} tables")

            for row in table_rows:
                table_name = row["TABLE_NAME"]

                # Extract columns for this table
                columns = self._extract_columns(cursor, table_name)

                # Extract indexes for this table
                indexes = self._extract_indexes(cursor, table_name)

                # Parse Chinese name from comment
                chinese_name, description = self._parse_comment(row["TABLE_COMMENT"])

                # Determine primary key columns
                pk_columns = [col.name for col in columns if col.is_pk]

                table = TableMeta(
                    name=table_name,
                    schema_name=self.config.database,
                    chinese_name=chinese_name,
                    description=description or row["TABLE_COMMENT"],
                    row_count=row["TABLE_ROWS"] or 0,
                    is_view=(row["TABLE_TYPE"] == "VIEW"),
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
                COLUMN_NAME,
                COLUMN_TYPE,
                DATA_TYPE,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION,
                NUMERIC_SCALE,
                IS_NULLABLE,
                COLUMN_KEY,
                COLUMN_DEFAULT,
                COLUMN_COMMENT,
                ORDINAL_POSITION,
                EXTRA
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """,
            (self.config.database, table_name),
        )

        columns = []
        for row in cursor.fetchall():
            chinese_name, col_description = self._parse_comment(row["COLUMN_COMMENT"])

            # Parse enum values if applicable
            enum_values = self._parse_enum_values(row["COLUMN_TYPE"])

            column = ColumnMeta(
                name=row["COLUMN_NAME"],
                chinese_name=chinese_name,
                data_type=row["COLUMN_TYPE"],
                base_type=row["DATA_TYPE"],
                length=row["CHARACTER_MAXIMUM_LENGTH"],
                precision=row["NUMERIC_PRECISION"],
                scale=row["NUMERIC_SCALE"],
                is_pk=(row["COLUMN_KEY"] == "PRI"),
                is_nullable=(row["IS_NULLABLE"] == "YES"),
                is_unique=(row["COLUMN_KEY"] == "UNI"),
                default_value=row["COLUMN_DEFAULT"],
                description=col_description or row["COLUMN_COMMENT"],
                ordinal_position=row["ORDINAL_POSITION"],
                enum_values=enum_values,
            )
            columns.append(column)

        return columns

    def _extract_indexes(self, cursor: Any, table_name: str) -> list[IndexMeta]:
        """Extract indexes for a specific table."""
        cursor.execute(
            """
            SELECT 
                INDEX_NAME,
                COLUMN_NAME,
                NON_UNIQUE,
                INDEX_TYPE
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY INDEX_NAME, SEQ_IN_INDEX
            """,
            (self.config.database, table_name),
        )

        # Group columns by index name
        index_map: dict[str, dict] = {}
        for row in cursor.fetchall():
            idx_name = row["INDEX_NAME"]
            if idx_name not in index_map:
                index_map[idx_name] = {
                    "name": idx_name,
                    "columns": [],
                    "is_unique": row["NON_UNIQUE"] == 0,
                    "is_primary": idx_name == "PRIMARY",
                    "index_type": row["INDEX_TYPE"],
                }
            index_map[idx_name]["columns"].append(row["COLUMN_NAME"])

        return [
            IndexMeta(
                name=data["name"],
                columns=data["columns"],
                is_unique=data["is_unique"],
                is_primary=data["is_primary"],
                index_type=data["index_type"],
            )
            for data in index_map.values()
        ]

    def extract_foreign_keys(self) -> list[ForeignKeyMeta]:
        """Extract all foreign key relationships."""
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 
                    CONSTRAINT_NAME,
                    TABLE_NAME,
                    COLUMN_NAME,
                    REFERENCED_TABLE_NAME,
                    REFERENCED_COLUMN_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = %s
                  AND REFERENCED_TABLE_NAME IS NOT NULL
                ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION
                """,
                (self.config.database,),
            )

            foreign_keys = []
            for row in cursor.fetchall():
                # Get referential actions
                delete_rule, update_rule = self._get_referential_actions(
                    cursor, row["CONSTRAINT_NAME"]
                )

                fk = ForeignKeyMeta(
                    constraint_name=row["CONSTRAINT_NAME"],
                    from_table=row["TABLE_NAME"],
                    from_column=row["COLUMN_NAME"],
                    to_table=row["REFERENCED_TABLE_NAME"],
                    to_column=row["REFERENCED_COLUMN_NAME"],
                    on_delete=delete_rule,
                    on_update=update_rule,
                )
                foreign_keys.append(fk)

            return foreign_keys

    def _get_referential_actions(
        self, cursor: Any, constraint_name: str
    ) -> tuple[str, str]:
        """Get ON DELETE and ON UPDATE actions for a foreign key."""
        cursor.execute(
            """
            SELECT DELETE_RULE, UPDATE_RULE
            FROM information_schema.REFERENTIAL_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = %s AND CONSTRAINT_NAME = %s
            """,
            (self.config.database, constraint_name),
        )
        row = cursor.fetchone()
        if row:
            return row["DELETE_RULE"], row["UPDATE_RULE"]
        return "RESTRICT", "RESTRICT"

    def _parse_comment(self, comment: str | None) -> tuple[str | None, str | None]:
        """
        Parse Chinese name and description from comment.

        Handles formats like:
        - "中文名"
        - "中文名-描述"
        - "中文名: 描述"
        - "中文名（描述）"
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

    def _parse_enum_values(self, column_type: str) -> list[str]:
        """Parse enum values from column type like enum('a','b','c')."""
        if not column_type.startswith("enum("):
            return []

        match = re.match(r"enum\((.+)\)", column_type)
        if match:
            values_str = match.group(1)
            # Extract values between quotes
            values = re.findall(r"'([^']*)'", values_str)
            return values
        return []


# Register the extractor with the factory
ExtractorFactory.register("mysql", MySQLSchemaExtractor)
