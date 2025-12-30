"""
SQL Server metadata provider for EasySql.

Provides SQL Server-specific implementations for retrieving metadata
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


class SQLServerMetadataProvider(DBMetadataProvider):
    """
    SQL Server-specific metadata provider.

    Handles:
    - Table/column comments via sys.extended_properties
    - Row count estimates from sys.dm_db_partition_stats
    
    Note: SQL Server doesn't have native enum types.
    Extended properties with name 'MS_Description' are used for comments.
    """

    def __init__(self, engine: "Engine"):
        super().__init__(engine)
        self._table_comments_cache: dict[tuple[str, str], str | None] = {}
        self._column_comments_cache: dict[tuple[str, str, str], str | None] = {}

    def get_table_comment(self, schema: str, table_name: str) -> str | None:
        """Get table comment from sys.extended_properties."""
        cache_key = (schema, table_name)
        if cache_key in self._table_comments_cache:
            return self._table_comments_cache[cache_key]

        query = text("""
            SELECT CAST(ep.value AS NVARCHAR(MAX)) as comment
            FROM sys.extended_properties ep
            INNER JOIN sys.tables t ON ep.major_id = t.object_id
            INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
            WHERE s.name = :schema 
              AND t.name = :table_name
              AND ep.name = 'MS_Description'
              AND ep.minor_id = 0
        """)

        with self.engine.connect() as conn:
            try:
                result = conn.execute(
                    query, {"schema": schema, "table_name": table_name}
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
        """Get column comment from sys.extended_properties."""
        cache_key = (schema, table_name, column_name)
        if cache_key in self._column_comments_cache:
            return self._column_comments_cache[cache_key]

        query = text("""
            SELECT CAST(ep.value AS NVARCHAR(MAX)) as comment
            FROM sys.extended_properties ep
            INNER JOIN sys.tables t ON ep.major_id = t.object_id
            INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
            INNER JOIN sys.columns c ON ep.major_id = c.object_id 
                                     AND ep.minor_id = c.column_id
            WHERE s.name = :schema 
              AND t.name = :table_name
              AND c.name = :column_name
              AND ep.name = 'MS_Description'
        """)

        with self.engine.connect() as conn:
            try:
                result = conn.execute(
                    query,
                    {
                        "schema": schema,
                        "table_name": table_name,
                        "column_name": column_name,
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
        SQL Server doesn't have native enum types.

        Returns:
            Empty list (SQL Server uses CHECK constraints for enum-like behavior)
        """
        return []

    def get_row_count(self, schema: str, table_name: str) -> int:
        """Get estimated row count from sys.dm_db_partition_stats."""
        query = text("""
            SELECT SUM(p.row_count) as row_count
            FROM sys.dm_db_partition_stats p
            INNER JOIN sys.tables t ON p.object_id = t.object_id
            INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
            WHERE s.name = :schema 
              AND t.name = :table_name
              AND p.index_id IN (0, 1)  -- Heap or clustered index
        """)

        with self.engine.connect() as conn:
            try:
                result = conn.execute(
                    query, {"schema": schema, "table_name": table_name}
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
            SELECT 
                c.name as column_name,
                CAST(ep.value AS NVARCHAR(MAX)) as comment
            FROM sys.columns c
            INNER JOIN sys.tables t ON c.object_id = t.object_id
            INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
            LEFT JOIN sys.extended_properties ep 
                ON ep.major_id = c.object_id 
               AND ep.minor_id = c.column_id
               AND ep.name = 'MS_Description'
            WHERE s.name = :schema AND t.name = :table_name
            ORDER BY c.column_id
        """)

        result_dict: dict[str, str | None] = {}
        with self.engine.connect() as conn:
            try:
                result = conn.execute(
                    query, {"schema": schema, "table_name": table_name}
                )
                for row in result:
                    column_name = row[0]
                    comment = row[1] if row[1] else None
                    result_dict[column_name] = comment
                    # Also populate cache
                    self._column_comments_cache[(schema, table_name, column_name)] = comment
            except Exception as e:
                logger.debug(
                    f"Failed to batch get column comments for {schema}.{table_name}: {e}"
                )

        return result_dict


# Register the provider with the factory
MetadataProviderFactory.register("sqlserver", SQLServerMetadataProvider)
