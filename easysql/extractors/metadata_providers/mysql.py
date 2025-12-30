"""
MySQL metadata provider for EasySql.

Provides MySQL-specific implementations for retrieving metadata
that SQLAlchemy Inspector doesn't support uniformly.
"""

import re
from typing import TYPE_CHECKING

from sqlalchemy import text

from easysql.extractors.metadata_providers.base import (
    DBMetadataProvider,
    MetadataProviderFactory,
)
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = get_logger(__name__)


class MySQLMetadataProvider(DBMetadataProvider):
    """
    MySQL-specific metadata provider.

    Handles:
    - Table/column comments via information_schema
    - Enum value parsing from column type
    - Row count estimates from TABLE_ROWS
    """

    def __init__(self, engine: "Engine"):
        super().__init__(engine)
        self._table_comments_cache: dict[tuple[str, str], str | None] = {}
        self._column_comments_cache: dict[tuple[str, str, str], str | None] = {}

    def get_table_comment(self, schema: str, table_name: str) -> str | None:
        """Get table comment from information_schema.TABLES."""
        cache_key = (schema, table_name)
        if cache_key in self._table_comments_cache:
            return self._table_comments_cache[cache_key]

        query = text("""
            SELECT TABLE_COMMENT
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table_name
        """)

        with self.engine.connect() as conn:
            result = conn.execute(query, {"schema": schema, "table_name": table_name})
            row = result.fetchone()
            comment = row[0] if row and row[0] else None
            self._table_comments_cache[cache_key] = comment
            return comment

    def get_column_comment(
        self, schema: str, table_name: str, column_name: str
    ) -> str | None:
        """Get column comment from information_schema.COLUMNS."""
        cache_key = (schema, table_name, column_name)
        if cache_key in self._column_comments_cache:
            return self._column_comments_cache[cache_key]

        query = text("""
            SELECT COLUMN_COMMENT
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = :schema 
              AND TABLE_NAME = :table_name 
              AND COLUMN_NAME = :column_name
        """)

        with self.engine.connect() as conn:
            result = conn.execute(
                query,
                {"schema": schema, "table_name": table_name, "column_name": column_name},
            )
            row = result.fetchone()
            comment = row[0] if row and row[0] else None
            self._column_comments_cache[cache_key] = comment
            return comment

    def get_enum_values(self, column_type: str, udt_name: str | None = None) -> list[str]:
        """
        Parse enum values from MySQL column type.

        Args:
            column_type: Column type like "enum('a','b','c')"
            udt_name: Not used for MySQL

        Returns:
            List of enum values
        """
        if not column_type or not column_type.lower().startswith("enum("):
            return []

        match = re.match(r"enum\((.+)\)", column_type, re.IGNORECASE)
        if match:
            values_str = match.group(1)
            # Extract values between quotes
            values = re.findall(r"'([^']*)'", values_str)
            return values
        return []

    def get_row_count(self, schema: str, table_name: str) -> int:
        """Get estimated row count from information_schema.TABLES."""
        query = text("""
            SELECT TABLE_ROWS
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table_name
        """)

        with self.engine.connect() as conn:
            result = conn.execute(query, {"schema": schema, "table_name": table_name})
            row = result.fetchone()
            return int(row[0]) if row and row[0] else 0

    def get_column_type(self, schema: str, table_name: str, column_name: str) -> str | None:
        """
        Get the full column type (e.g., 'enum(...)', 'varchar(255)').

        This is useful because SQLAlchemy Inspector may not preserve
        the exact column type string for enum types.
        """
        query = text("""
            SELECT COLUMN_TYPE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = :schema 
              AND TABLE_NAME = :table_name 
              AND COLUMN_NAME = :column_name
        """)

        with self.engine.connect() as conn:
            result = conn.execute(
                query,
                {"schema": schema, "table_name": table_name, "column_name": column_name},
            )
            row = result.fetchone()
            return row[0] if row else None

    def batch_get_column_metadata(
        self, schema: str, table_name: str
    ) -> dict[str, dict]:
        """
        Batch retrieve column comments and types for a table.

        This is more efficient than calling get_column_comment
        for each column individually.

        Returns:
            Dict mapping column_name to {comment, column_type}
        """
        query = text("""
            SELECT COLUMN_NAME, COLUMN_COMMENT, COLUMN_TYPE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table_name
            ORDER BY ORDINAL_POSITION
        """)

        result_dict: dict[str, dict] = {}
        with self.engine.connect() as conn:
            result = conn.execute(query, {"schema": schema, "table_name": table_name})
            for row in result:
                column_name = row[0]
                result_dict[column_name] = {
                    "comment": row[1] if row[1] else None,
                    "column_type": row[2],
                }
                # Also populate cache
                self._column_comments_cache[(schema, table_name, column_name)] = row[1]

        return result_dict


# Register the provider with the factory
MetadataProviderFactory.register("mysql", MySQLMetadataProvider)
