"""
Unified SQLAlchemy schema extractor for EasySql.

Uses SQLAlchemy Inspector to extract schema metadata from any supported database,
delegating database-specific tasks (like comments) to metadata providers.
"""

from typing import TYPE_CHECKING

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine, Inspector

from easysql.config import DatabaseConfig
from easysql.extractors.base import BaseSchemaExtractor
from easysql.extractors.metadata_providers import MetadataProviderFactory
from easysql.models.schema import (
    ColumnMeta,
    DatabaseMeta,
    DatabaseType,
    ForeignKeyMeta,
    IndexMeta,
    TableMeta,
)
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from easysql.extractors.metadata_providers.base import DBMetadataProvider

logger = get_logger(__name__)


class SQLAlchemySchemaExtractor(BaseSchemaExtractor):
    """
    Unified schema extractor using SQLAlchemy Inspector.

    This extractor replaces the hand-written SQL in previous extractors,
    providing a more maintainable and cross-database solution.
    It delegates database-specific metadata extraction (comments, enums)
    to the appropriate DBMetadataProvider.
    """

    def __init__(self, config: DatabaseConfig):
        super().__init__(config)
        self._engine: Engine | None = None
        self._inspector: Inspector | None = None
        self._metadata_provider: "DBMetadataProvider | None" = None
        self._schema: str | None = None

    @property
    def inspector(self) -> Inspector:
        """Get inspector, raising if not connected."""
        if self._inspector is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._inspector

    @property
    def metadata_provider(self) -> "DBMetadataProvider":
        """Get metadata provider, raising if not connected."""
        if self._metadata_provider is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._metadata_provider

    @property
    def db_type(self) -> DatabaseType:
        return DatabaseType(self.config.db_type)

    def connect(self) -> None:
        """Establish connection and initialize inspector."""
        try:
            self._engine = create_engine(self.config.get_connection_string())
            self._inspector = inspect(self._engine)
            self._metadata_provider = MetadataProviderFactory.create(
                self.config.db_type, self._engine
            )
            # Determine schema to use
            self._schema = self._resolve_schema()
            logger.debug(
                f"Connected to {self.config.db_type}: {self.config.host}:{self.config.port}, schema={self._schema}"
            )
        except Exception as e:
            logger.error(f"Failed to connect to {self.config.db_type}: {e}")
            raise ConnectionError(f"Connection failed: {e}") from e

    def _resolve_schema(self) -> str:
        """Resolve the schema to use for extraction."""
        # Use config schema if provided
        schema = self.config.get_default_schema()

        # Validate schema exists (for non-MySQL databases)
        if self.config.db_type != "mysql":
            try:
                available_schemas = self.inspector.get_schema_names()
                if schema not in available_schemas:
                    logger.warning(
                        f"Schema '{schema}' not found, available: {available_schemas}. "
                        f"Using default schema."
                    )
                    # Fallback to first available or default
                    if "public" in available_schemas:
                        schema = "public"
                    elif "dbo" in available_schemas:
                        schema = "dbo"
                    elif available_schemas:
                        schema = available_schemas[0]
            except Exception as e:
                logger.debug(f"Could not validate schema: {e}")

        return schema

    def disconnect(self) -> None:
        """Close the database connection."""
        if self._engine:
            self._engine.dispose()
            self._engine = None
            self._inspector = None
            self._metadata_provider = None
            self._schema = None
            logger.debug("Database connection closed")

    def extract_tables(self) -> list[TableMeta]:
        """Extract all tables using SQLAlchemy Inspector."""
        tables = []
        schema = self._schema or ""

        # Get table names
        try:
            table_names = self.inspector.get_table_names(schema=schema or None)
        except Exception as e:
            logger.warning(f"Failed to get tables for schema {schema}: {e}")
            table_names = self.inspector.get_table_names()

        logger.debug(f"Found {len(table_names)} tables in schema {schema}")

        for table_name in table_names:
            try:
                table = self._extract_single_table(schema, table_name, is_view=False)
                tables.append(table)
            except Exception as e:
                logger.warning(f"Failed to extract table {table_name}: {e}")
                continue

        # Extract views
        try:
            view_names = self.inspector.get_view_names(schema=schema or None)
            logger.debug(f"Found {len(view_names)} views in schema {schema}")
            for view_name in view_names:
                try:
                    view = self._extract_single_table(schema, view_name, is_view=True)
                    tables.append(view)
                except Exception as e:
                    logger.warning(f"Failed to extract view {view_name}: {e}")
                    continue
        except Exception as e:
            logger.debug(f"View extraction not supported or failed: {e}")

        return tables

    def _extract_single_table(self, schema: str, table_name: str, is_view: bool) -> TableMeta:
        """Extract metadata for a single table or view."""
        # 1. Basic Metadata from provider
        table_comment = self.metadata_provider.get_table_comment(schema, table_name)
        chinese_name, description = self.metadata_provider.parse_comment(table_comment)
        row_count = 0 if is_view else self.metadata_provider.get_row_count(schema, table_name)

        # 2. Indexes (before columns, to mark is_indexed)
        indexes = [] if is_view else self._extract_indexes(schema, table_name)
        indexed_columns = set()
        for idx in indexes:
            indexed_columns.update(idx.columns)

        # 3. Unique constraints (to properly handle single-column vs composite)
        unique_constraints = []
        single_col_unique = set()
        if not is_view:
            try:
                uc_list = self.inspector.get_unique_constraints(table_name, schema=schema)
                for uc in uc_list:
                    cols = uc.get("column_names", [])
                    if cols:
                        unique_constraints.append(cols)
                        if len(cols) == 1:
                            single_col_unique.add(cols[0])
            except Exception as e:
                logger.debug(f"Failed to get unique constraints for {table_name}: {e}")

        # 4. Primary Keys
        pk_columns = []
        if not is_view:
            try:
                pk_constraint = self.inspector.get_pk_constraint(table_name, schema=schema)
                pk_columns = pk_constraint.get("constrained_columns", [])
            except Exception as e:
                logger.debug(f"Failed to get PK for {table_name}: {e}")

        # 5. Columns (with is_indexed and is_unique properly set)
        columns = self._extract_columns(
            schema, table_name, indexed_columns, single_col_unique, set(pk_columns)
        )

        return TableMeta(
            name=table_name,
            schema_name=schema,
            chinese_name=chinese_name,
            description=description or table_comment,
            row_count=row_count,
            is_view=is_view,
            primary_key=pk_columns,
            unique_constraints=unique_constraints,
            columns=columns,
            indexes=indexes,
        )

    def _extract_columns(
        self,
        schema: str,
        table_name: str,
        indexed_columns: set[str],
        single_col_unique: set[str],
        pk_columns: set[str],
    ) -> list[ColumnMeta]:
        """Extract columns using Inspector and Provider."""
        sa_columns = self.inspector.get_columns(table_name, schema=schema)

        # Batch get column metadata (comments + types) if supported
        column_metadata = {}
        if hasattr(self.metadata_provider, "batch_get_column_metadata"):
            column_metadata = self.metadata_provider.batch_get_column_metadata(schema, table_name)
        elif hasattr(self.metadata_provider, "batch_get_column_comments"):
            # Fallback to just comments
            comments = self.metadata_provider.batch_get_column_comments(schema, table_name)
            column_metadata = {name: {"comment": c} for name, c in comments.items()}

        columns = []
        for i, col in enumerate(sa_columns):
            name = col["name"]
            sa_type = col["type"]
            default = col.get("default")
            nullable = col.get("nullable", True)

            # Get metadata from batch or individual call
            col_meta = column_metadata.get(name, {})
            comment = col_meta.get("comment")
            if comment is None:
                comment = self.metadata_provider.get_column_comment(schema, table_name, name)

            chinese_name, col_description = self.metadata_provider.parse_comment(comment)

            # Data type: prefer provider's exact type if available (for MySQL enum)
            data_type_str = col_meta.get("column_type") or str(sa_type).lower()
            base_type = data_type_str.split("(")[0].strip()

            # Enum values
            enum_values: list[str] = []
            enums_attr = getattr(sa_type, "enums", None)
            if enums_attr:
                enum_values = list(enums_attr)
            else:
                # Try provider for enum values
                enum_values = self.metadata_provider.get_enum_values(
                    data_type_str, udt_name=getattr(sa_type, "name", None)
                )

            # Length/Precision/Scale
            length = getattr(sa_type, "length", None)
            precision = getattr(sa_type, "precision", None)
            scale = getattr(sa_type, "scale", None)

            column = ColumnMeta(
                name=name,
                chinese_name=chinese_name,
                data_type=data_type_str,
                base_type=base_type,
                length=length,
                precision=precision,
                scale=scale,
                is_pk=(name in pk_columns),
                is_nullable=nullable,
                is_indexed=(name in indexed_columns),
                is_unique=(name in single_col_unique),
                default_value=str(default) if default is not None else None,
                description=col_description or comment,
                ordinal_position=i + 1,
                enum_values=enum_values,
            )
            columns.append(column)

        return columns

    def _extract_indexes(self, schema: str, table_name: str) -> list[IndexMeta]:
        """Extract indexes using Inspector."""
        try:
            sa_indexes = self.inspector.get_indexes(table_name, schema=schema)
        except Exception as e:
            logger.debug(f"Failed to get indexes for {table_name}: {e}")
            return []

        indexes = []
        for idx in sa_indexes:
            index_type = "BTREE"
            # Try to get index type from dialect options
            dialect_opts = idx.get("dialect_options", {})
            if "mysql_using" in dialect_opts:
                index_type = dialect_opts["mysql_using"].upper()
            elif "postgresql_using" in dialect_opts:
                index_type = dialect_opts["postgresql_using"].upper()

            # Filter out None values from column_names
            column_names = [c for c in idx.get("column_names", []) if c is not None]

            indexes.append(
                IndexMeta(
                    name=idx["name"] or f"idx_{table_name}",
                    columns=column_names,
                    is_unique=idx.get("unique", False),
                    is_primary=False,
                    index_type=index_type,
                )
            )
        return indexes

    def extract_foreign_keys(self) -> list[ForeignKeyMeta]:
        """Extract foreign keys for all tables."""
        foreign_keys = []
        schema = self._schema

        try:
            table_names = self.inspector.get_table_names(schema=schema)
        except Exception:
            table_names = self.inspector.get_table_names()

        for table_name in table_names:
            try:
                fks = self.inspector.get_foreign_keys(table_name, schema=schema)
                for fk in fks:
                    constrained_columns = fk.get("constrained_columns", [])
                    referred_columns = fk.get("referred_columns", [])
                    referred_table = fk.get("referred_table", "")
                    # Get referred schema (defaults to current schema if not specified)
                    referred_schema = fk.get("referred_schema") or schema

                    # Handle composite keys by creating multiple metadata entries
                    for i, col_name in enumerate(constrained_columns):
                        ref_col_name = referred_columns[i] if i < len(referred_columns) else ""

                        foreign_keys.append(
                            ForeignKeyMeta(
                                constraint_name=fk.get("name") or f"fk_{table_name}_{col_name}",
                                from_schema=schema or "",
                                from_table=table_name,
                                from_column=col_name,
                                to_schema=str(referred_schema) if referred_schema else "",
                                to_table=referred_table,
                                to_column=ref_col_name,
                                on_delete=fk.get("options", {}).get("ondelete", "RESTRICT"),
                                on_update=fk.get("options", {}).get("onupdate", "RESTRICT"),
                            )
                        )
            except Exception as e:
                logger.warning(f"Failed to extract foreign keys for {table_name}: {e}")
                continue

        return foreign_keys
