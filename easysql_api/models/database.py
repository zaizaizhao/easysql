"""API contracts for user-managed data-plane database configurations."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

SUPPORTED_DATABASE_TYPES = {"mysql", "postgresql", "oracle", "sqlserver"}
SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


class DatabaseConfigInput(BaseModel):
    """A database configuration accepted from the settings page.

    ``password=None`` means "keep the existing password" when replacing an
    existing logical database. The password is never returned by read APIs.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=64)
    db_type: str = Field(
        default="postgresql",
        validation_alias=AliasChoices("db_type", "type"),
        serialization_alias="type",
    )
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(default=5432, ge=1, le=65535)
    user: str = Field(..., min_length=1, max_length=128)
    password: str | None = Field(default=None, max_length=4096)
    database: str = Field(..., min_length=1, max_length=128)
    schema_name: str | None = Field(
        default=None,
        max_length=128,
        validation_alias=AliasChoices("schema_name", "schema"),
    )
    system_type: str = Field(default="UNKNOWN", max_length=64)
    description: str = Field(default="", max_length=1000)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not SAFE_NAME_PATTERN.fullmatch(normalized):
            raise ValueError(
                "name must start with a letter and contain only letters, numbers, or underscores"
            )
        return normalized

    @field_validator("db_type")
    @classmethod
    def validate_db_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_DATABASE_TYPES:
            raise ValueError(
                f"db_type must be one of: {', '.join(sorted(SUPPORTED_DATABASE_TYPES))}"
            )
        return normalized

    @field_validator("host", "user", "database")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("schema_name")
    @classmethod
    def validate_optional_identifier(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = value.strip()
        if not SAFE_NAME_PATTERN.fullmatch(normalized):
            raise ValueError("value must contain only letters, numbers, or underscores")
        return normalized


class DatabaseConfigView(BaseModel):
    """Public database configuration without credentials."""

    name: str
    type: str
    host: str
    port: int
    user: str
    database: str
    schema_name: str = Field(
        validation_alias=AliasChoices("schema_name", "schema"),
        serialization_alias="schema",
    )
    system_type: str
    description: str
    dblink_connection_name: str
    has_password: bool


class DatabaseConfigListResponse(BaseModel):
    databases: list[DatabaseConfigView]
    total: int


class DatabaseConfigUpdateRequest(BaseModel):
    databases: list[DatabaseConfigInput] = Field(default_factory=list, max_length=100)


class DatabaseConfigUpdateResponse(DatabaseConfigListResponse):
    updated: list[str]


class DatabaseConnectionTestResponse(BaseModel):
    success: bool
    message: str


class DatabaseFederationStatusRequest(BaseModel):
    db_names: list[str] = Field(..., min_length=1, max_length=100)


class DblinkRouteStatusView(BaseModel):
    source_db: str
    target_db: str
    status: Literal["ready", "unavailable"]
    reason: str


class DatabaseDblinkStatusView(BaseModel):
    name: str
    connection_name: str
    status: Literal["not_required", "ready", "unavailable"]
    reason: str
    extension_installed: bool | None
    connect_allowed: bool | None
    routes: list[DblinkRouteStatusView] = Field(default_factory=list)


class DatabaseFederationStatusResponse(BaseModel):
    mode: Literal["single", "dblink"]
    status: Literal["not_required", "ready", "unavailable"]
    reason: str
    db_names: list[str]
    databases: list[DatabaseDblinkStatusView]
