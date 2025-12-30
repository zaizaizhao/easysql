"""
Oracle metadata provider for EasySql.

Provides Oracle-specific implementations for retrieving metadata
that SQLAlchemy Inspector doesn't support uniformly.
"""

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


class OracleMetadataProvider(DBMetadataProvider):
    """
    Oracle-specific metadata provider.

    Handles:
    - Table/column comments via ALL_TAB_COMMENTS/ALL_COL_COMMENTS
    - Row count estimates from ALL_TABLES.NUM_ROWS
    
    Note: Oracle doesn't have native enum types like MySQL/PostgreSQL.
    """

    def __init__(self, engine: "Engine"):
        super().__init__(engine)
        self._table_comments_cache: dict[tuple[str, str], str | None] = {}
        self._column_comments_cache: dict[tuple[str, str, str], str | None] = {}

    def get_table_comment(self, schema: str, table_name: str) -> str | None:
        """Get table comment from ALL_TAB_COMMENTS."""
        cache_key = (schema.upper(), table_name.upper())
        if cache_key in self._table_comments_cache:
            return self._table_comments_cache[cache_key]

        query = text("""
            SELECT COMMENTS
            FROM ALL_TAB_COMMENTS
            WHERE OWNER = :schema AND TABLE_NAME = :table_name
        """)

        with self.engine.connect() as conn:
            try:
                result = conn.execute(
                    query, {"schema": schema.upper(), "table_name": table_name.upper()}
                )
                row = result.fetchone()
                comment = row[0] if row and row[0] else None
                self._table_comments_cache[cache_key] = comment
                return comment
            except Exception as e:
                logger.debug(f"Failed to get table comment for {schema}.{table_name}: {e}")
                return None

    def get_column_comment(
        self, schema: str, table_name: str, column_name: str
    ) -> str | None:
        """Get column comment from ALL_COL_COMMENTS."""
        cache_key = (schema.upper(), table_name.upper(), column_name.upper())
        if cache_key in self._column_comments_cache:
            return self._column_comments_cache[cache_key]

        query = text("""
            SELECT COMMENTS
            FROM ALL_COL_COMMENTS
            WHERE OWNER = :schema 
              AND TABLE_NAME = :table_name 
              AND COLUMN_NAME = :column_name
        """)

        with self.engine.connect() as conn:
            try:
                result = conn.execute(
                    query,
                    {
                        "schema": schema.upper(),
                        "table_name": table_name.upper(),
                        "column_name": column_name.upper(),
                    },
                )
                row = result.fetchone()
                comment = row[0] if row and row[0] else None
                self._column_comments_cache[cache_key] = comment
                return comment
            except Exception as e:
                logger.debug(
                    f"Failed to get column comment for {schema}.{table_name}.{column_name}: {e}"
                )
                return None

    def get_enum_values(self, column_type: str, udt_name: str | None = None) -> list[str]:
        """
        Oracle doesn't have native enum types.

        Returns:
            Empty list (Oracle uses CHECK constraints for enum-like behavior)
        """
        return []

    def get_row_count(self, schema: str, table_name: str) -> int:
        """Get estimated row count from ALL_TABLES.NUM_ROWS."""
        query = text("""
            SELECT NUM_ROWS
            FROM ALL_TABLES
            WHERE OWNER = :schema AND TABLE_NAME = :table_name
        """)

        with self.engine.connect() as conn:
            try:
                result = conn.execute(
                    query, {"schema": schema.upper(), "table_name": table_name.upper()}
                )
                row = result.fetchone()
                return int(row[0]) if row and row[0] else 0
            except Exception as e:
                logger.debug(f"Failed to get row count for {schema}.{table_name}: {e}")
                return 0

    def batch_get_column_comments(
        self, schema: str, table_name: str
    ) -> dict[str, str | None]:
        """
        Batch retrieve column comments for a table.

        Returns:
            Dict mapping column_name to comment
        """
        query = text("""
            SELECT COLUMN_NAME, COMMENTS
            FROM ALL_COL_COMMENTS
            WHERE OWNER = :schema AND TABLE_NAME = :table_name
        """)

        result_dict: dict[str, str | None] = {}
        with self.engine.connect() as conn:
            try:
                result = conn.execute(
                    query, {"schema": schema.upper(), "table_name": table_name.upper()}
                )
                for row in result:
                    column_name = row[0]
                    comment = row[1] if row[1] else None
                    result_dict[column_name] = comment
                    # Also populate cache (Oracle uses uppercase)
                    self._column_comments_cache[
                        (schema.upper(), table_name.upper(), column_name)
                    ] = comment
            except Exception as e:
                logger.debug(
                    f"Failed to batch get column comments for {schema}.{table_name}: {e}"
                )

        return result_dict


# Register the provider with the factory
MetadataProviderFactory.register("oracle", OracleMetadataProvider)
