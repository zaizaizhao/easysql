"""
PostgreSQL metadata provider for EasySql.

Provides PostgreSQL-specific implementations for retrieving metadata
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


class PostgreSQLMetadataProvider(DBMetadataProvider):
    """
    PostgreSQL-specific metadata provider.

    Handles:
    - Table/column comments via pg_catalog functions
    - Enum values from pg_enum system table
    - Row count estimates from pg_class.reltuples
    """

    def __init__(self, engine: "Engine"):
        super().__init__(engine)
        self._table_comments_cache: dict[tuple[str, str], str | None] = {}
        self._column_comments_cache: dict[tuple[str, str, str], str | None] = {}
        self._enum_values_cache: dict[str, list[str]] = {}

    def get_table_comment(self, schema: str, table_name: str) -> str | None:
        """Get table comment using pg_catalog.obj_description."""
        cache_key = (schema, table_name)
        if cache_key in self._table_comments_cache:
            return self._table_comments_cache[cache_key]

        query = text("""
            SELECT pg_catalog.obj_description(
                (quote_ident(:schema) || '.' || quote_ident(:table_name))::regclass,
                'pg_class'
            ) as table_comment
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
        """Get column comment using pg_catalog.col_description."""
        cache_key = (schema, table_name, column_name)
        if cache_key in self._column_comments_cache:
            return self._column_comments_cache[cache_key]

        query = text("""
            SELECT pg_catalog.col_description(
                (quote_ident(:schema) || '.' || quote_ident(:table_name))::regclass,
                (SELECT ordinal_position 
                 FROM information_schema.columns 
                 WHERE table_schema = :schema 
                   AND table_name = :table_name 
                   AND column_name = :column_name)
            ) as column_comment
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
        Get enum values for a PostgreSQL user-defined enum type.

        Args:
            column_type: Column type (usually 'USER-DEFINED' for enums)
            udt_name: The enum type name

        Returns:
            List of enum values
        """
        if not udt_name:
            return []

        if udt_name in self._enum_values_cache:
            return self._enum_values_cache[udt_name]

        query = text("""
            SELECT enumlabel
            FROM pg_enum
            JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
            WHERE pg_type.typname = :enum_name
            ORDER BY enumsortorder
        """)

        with self.engine.connect() as conn:
            try:
                result = conn.execute(query, {"enum_name": udt_name})
                values = [row[0] for row in result]
                self._enum_values_cache[udt_name] = values
                return values
            except Exception as e:
                logger.debug(f"Failed to get enum values for {udt_name}: {e}")
                return []

    def get_row_count(self, schema: str, table_name: str) -> int:
        """Get estimated row count from pg_class.reltuples."""
        query = text("""
            SELECT reltuples::bigint as row_count
            FROM pg_class
            WHERE oid = (quote_ident(:schema) || '.' || quote_ident(:table_name))::regclass
        """)

        with self.engine.connect() as conn:
            try:
                result = conn.execute(
                    query, {"schema": schema, "table_name": table_name}
                )
                row = result.fetchone()
                return int(row[0]) if row and row[0] and row[0] > 0 else 0
            except Exception as e:
                logger.debug(f"Failed to get row count for {schema}.{table_name}: {e}")
                return 0

    def batch_get_column_comments(
        self, schema: str, table_name: str
    ) -> dict[str, str | None]:
        """
        Batch retrieve column comments for a table.

        This is more efficient than calling get_column_comment
        for each column individually.

        Returns:
            Dict mapping column_name to comment
        """
        query = text("""
            SELECT 
                c.column_name,
                pg_catalog.col_description(
                    (quote_ident(c.table_schema) || '.' || quote_ident(c.table_name))::regclass,
                    c.ordinal_position
                ) as column_comment
            FROM information_schema.columns c
            WHERE c.table_schema = :schema AND c.table_name = :table_name
            ORDER BY c.ordinal_position
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

    def get_udt_name(self, schema: str, table_name: str, column_name: str) -> str | None:
        """
        Get the user-defined type name for a column.

        This is useful for identifying enum types.
        """
        query = text("""
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema = :schema 
              AND table_name = :table_name 
              AND column_name = :column_name
        """)

        with self.engine.connect() as conn:
            result = conn.execute(
                query,
                {"schema": schema, "table_name": table_name, "column_name": column_name},
            )
            row = result.fetchone()
            return row[0] if row else None


# Register the provider with the factory
MetadataProviderFactory.register("postgresql", PostgreSQLMetadataProvider)
