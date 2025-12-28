"""
Schema metadata models for EasySql.

Defines data models for database schema elements:
- Columns, Tables, Indexes, Foreign Keys
- Database metadata
"""

from enum import Enum

from pydantic import Field

from easysql.models.base import BaseModel


class DataType(str, Enum):
    """Common database data types."""

    VARCHAR = "varchar"
    CHAR = "char"
    TEXT = "text"
    INT = "int"
    BIGINT = "bigint"
    SMALLINT = "smallint"
    DECIMAL = "decimal"
    FLOAT = "float"
    DOUBLE = "double"
    BOOLEAN = "boolean"
    DATE = "date"
    TIME = "time"
    DATETIME = "datetime"
    TIMESTAMP = "timestamp"
    JSON = "json"
    BLOB = "blob"
    OTHER = "other"


class DatabaseType(str, Enum):
    """Supported database types."""

    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    ORACLE = "oracle"
    SQLSERVER = "sqlserver"


class ColumnMeta(BaseModel):
    """
    Column metadata model.

    Stores information about a database column including
    type, constraints, and descriptive metadata.
    """

    name: str = Field(..., description="Column name")
    chinese_name: str | None = Field(default=None, description="Chinese name from comment")
    data_type: str = Field(..., description="Data type (e.g., varchar(255))")
    base_type: str | None = Field(default=None, description="Base type without length")
    length: int | None = Field(default=None, description="Type length")
    precision: int | None = Field(default=None, description="Numeric precision")
    scale: int | None = Field(default=None, description="Numeric scale")
    is_pk: bool = Field(default=False, description="Is primary key")
    is_fk: bool = Field(default=False, description="Is foreign key")
    is_nullable: bool = Field(default=True, description="Is nullable")
    is_indexed: bool = Field(default=False, description="Has index")
    is_unique: bool = Field(default=False, description="Has unique constraint")
    default_value: str | None = Field(default=None, description="Default value")
    description: str | None = Field(default=None, description="Column comment/description")
    sample_values: list[str] = Field(default_factory=list, description="Sample values (anonymized)")
    enum_values: list[str] = Field(default_factory=list, description="Enum values if applicable")
    ordinal_position: int = Field(default=0, description="Column position in table")

    def get_id(self, db_name: str, table_name: str) -> str:
        """Generate unique column ID."""
        return f"{db_name}.{table_name}.{self.name}"

    def get_embedding_text(self) -> str:
        """Generate text for embedding."""
        parts = [self.name]
        if self.chinese_name:
            parts.append(self.chinese_name)
        if self.description:
            parts.append(self.description)
        parts.append(f"类型:{self.data_type}")
        if self.sample_values:
            parts.append(f"示例:{','.join(self.sample_values[:3])}")
        return " ".join(parts)


class IndexMeta(BaseModel):
    """
    Index metadata model.

    Stores information about database indexes.
    """

    name: str = Field(..., description="Index name")
    columns: list[str] = Field(default_factory=list, description="Indexed columns")
    is_unique: bool = Field(default=False, description="Is unique index")
    is_primary: bool = Field(default=False, description="Is primary key index")
    index_type: str = Field(default="BTREE", description="Index type (BTREE, HASH, etc.)")


class ForeignKeyMeta(BaseModel):
    """
    Foreign key metadata model.

    Stores information about foreign key relationships between tables.
    """

    constraint_name: str = Field(..., description="Constraint name")
    from_table: str = Field(..., description="Source table name")
    from_column: str = Field(..., description="Source column name")
    to_table: str = Field(..., description="Referenced table name")
    to_column: str = Field(..., description="Referenced column name")
    on_delete: str = Field(default="RESTRICT", description="ON DELETE action")
    on_update: str = Field(default="RESTRICT", description="ON UPDATE action")

    def get_id(self) -> str:
        """Generate unique foreign key ID."""
        return f"fk_{self.from_table}_{self.from_column}_{self.to_table}"


class TableMeta(BaseModel):
    """
    Table metadata model.

    Stores comprehensive information about a database table
    including columns, indexes, and descriptive metadata.
    """

    name: str = Field(..., description="Table name")
    schema_name: str = Field(default="public", description="Schema name")
    chinese_name: str | None = Field(default=None, description="Chinese name from comment")
    description: str | None = Field(default=None, description="Table comment/description")
    business_domain: str | None = Field(default=None, description="Business domain category")
    row_count: int = Field(default=0, description="Estimated row count")
    is_archive: bool = Field(default=False, description="Is archive/history table")
    is_view: bool = Field(default=False, description="Is view (not table)")
    primary_key: list[str] = Field(default_factory=list, description="Primary key columns")
    columns: list[ColumnMeta] = Field(default_factory=list, description="Table columns")
    indexes: list[IndexMeta] = Field(default_factory=list, description="Table indexes")

    def get_id(self, db_name: str) -> str:
        """Generate unique table ID."""
        return f"{db_name}.{self.schema_name}.{self.name}"

    def get_column(self, name: str) -> ColumnMeta | None:
        """Get column by name."""
        for col in self.columns:
            if col.name == name:
                return col
        return None

    def get_pk_columns(self) -> list[ColumnMeta]:
        """Get primary key columns."""
        return [col for col in self.columns if col.is_pk]

    def get_fk_columns(self) -> list[ColumnMeta]:
        """Get foreign key columns."""
        return [col for col in self.columns if col.is_fk]

    def get_core_columns_text(self, max_columns: int = 10) -> str:
        """Get text representation of core columns for embedding."""
        core_cols = []
        # Prioritize: PK, FK, then by position
        sorted_cols = sorted(
            self.columns, key=lambda c: (not c.is_pk, not c.is_fk, c.ordinal_position)
        )
        for col in sorted_cols[:max_columns]:
            if col.chinese_name:
                core_cols.append(f"{col.name}({col.chinese_name})")
            else:
                core_cols.append(col.name)
        return " ".join(core_cols)

    def get_embedding_text(self, db_name: str) -> str:
        """Generate text for embedding."""
        parts = [self.name]
        if self.chinese_name:
            parts.append(self.chinese_name)
        if self.description:
            parts.append(self.description)
        parts.append(self.get_core_columns_text())
        return " ".join(parts)


class DatabaseMeta(BaseModel):
    """
    Database metadata model.

    Stores comprehensive information about a database
    including all tables and their relationships.
    """

    name: str = Field(..., description="Database name")
    db_type: DatabaseType = Field(..., description="Database type")
    host: str = Field(..., description="Database host")
    port: int = Field(..., description="Database port")
    system_type: str = Field(default="UNKNOWN", description="System type (HIS, LIS, etc.)")
    description: str | None = Field(default=None, description="Database description")
    default_schema: str = Field(default="public", description="Default schema name")
    tables: list[TableMeta] = Field(default_factory=list, description="Database tables")
    foreign_keys: list[ForeignKeyMeta] = Field(default_factory=list, description="Foreign keys")

    def get_table(self, name: str) -> TableMeta | None:
        """Get table by name."""
        for table in self.tables:
            if table.name == name:
                return table
        return None

    def get_all_columns(self) -> list[tuple[str, ColumnMeta]]:
        """Get all columns with their table names."""
        result = []
        for table in self.tables:
            for col in table.columns:
                result.append((table.name, col))
        return result

    def get_statistics(self) -> dict:
        """Get database statistics."""
        total_columns = sum(len(t.columns) for t in self.tables)
        total_indexes = sum(len(t.indexes) for t in self.tables)
        return {
            "tables": len(self.tables),
            "columns": total_columns,
            "foreign_keys": len(self.foreign_keys),
            "indexes": total_indexes,
        }
