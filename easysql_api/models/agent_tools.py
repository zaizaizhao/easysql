"""HTTP contracts for the read-only external agent schema tools."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

SafeIdentifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,127}$",
    ),
]


class DatabaseScopeItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    db_type: str
    schema_name: str = Field(validation_alias="schema", serialization_alias="schema")
    system_type: str
    description: str
    dblink_connection_name: str
    supports_federation: bool


class DatabaseScopeResponse(BaseModel):
    databases: list[DatabaseScopeItem]
    total: int


class TableSearchRequest(BaseModel):
    db_name: SafeIdentifier
    query: str = Field(..., min_length=1, max_length=2_000)
    top_k: int = Field(default=5, ge=1, le=10)
    table_names: list[SafeIdentifier] | None = Field(default=None, max_length=10)


class TableMatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    database: str
    schema_name: str = Field(validation_alias="schema", serialization_alias="schema")
    table: str
    chinese_name: str | None = None
    description: str | None = None
    business_domain: str | None = None
    rank: int
    similarity_score: float


class TableSearchResponse(BaseModel):
    database: str
    query: str
    matches: list[TableMatch]
    elapsed_ms: float


class ColumnSearchRequest(BaseModel):
    db_name: SafeIdentifier
    query: str = Field(..., min_length=1, max_length=2_000)
    top_k: int = Field(default=10, ge=1, le=20)
    table_names: list[SafeIdentifier] | None = Field(default=None, max_length=10)


class ColumnMatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    database: str
    schema_name: str = Field(validation_alias="schema", serialization_alias="schema")
    table: str
    column: str
    qualified_table_id: str | None = None
    chinese_name: str | None = None
    data_type: str | None = None
    is_primary_key: bool
    is_foreign_key: bool
    rank: int
    similarity_score: float


class ColumnSearchResponse(BaseModel):
    database: str
    query: str
    matches: list[ColumnMatch]
    elapsed_ms: float


class TableSchemaRequest(BaseModel):
    db_name: SafeIdentifier
    table_names: list[SafeIdentifier] = Field(..., min_length=1, max_length=8)


class TableColumn(BaseModel):
    name: str
    chinese_name: str | None = None
    data_type: str | None = None
    base_type: str | None = None
    is_primary_key: bool
    is_foreign_key: bool
    is_nullable: bool | None = None
    is_indexed: bool | None = None
    is_unique: bool | None = None
    description: str | None = None
    ordinal_position: int | None = None


class TableSchemaItem(BaseModel):
    table: str
    columns: list[TableColumn]


class TableSchemaResponse(BaseModel):
    database: str
    tables: list[TableSchemaItem]
    missing_tables: list[str]
    elapsed_ms: float


class RelatedTableExpansionRequest(BaseModel):
    db_name: SafeIdentifier
    seed_tables: list[SafeIdentifier] = Field(..., min_length=1, max_length=5)
    max_depth: int = Field(default=1, ge=1, le=2)


class RelatedTableExpansionResponse(BaseModel):
    database: str
    seed_tables: list[str]
    added_tables: list[str]
    expanded_tables: list[str]
    max_depth: int
    elapsed_ms: float


class JoinPathRequest(BaseModel):
    db_name: SafeIdentifier
    table_names: list[SafeIdentifier] = Field(..., min_length=2, max_length=8)
    max_hops: int = Field(default=5, ge=1, le=5)


class JoinEdge(BaseModel):
    fk_table: str
    fk_column: str
    pk_table: str
    pk_column: str


class JoinPathResponse(BaseModel):
    database: str
    requested_tables: list[str]
    bridge_tables: list[str]
    edges: list[JoinEdge]
    max_hops: int
    elapsed_ms: float


class AgentToolErrorDetail(BaseModel):
    code: str
    message: str


class AgentToolErrorResponse(BaseModel):
    detail: AgentToolErrorDetail


JsonObject = dict[str, Any]
