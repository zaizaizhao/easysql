"""Grounded knowledge contracts shared by ingestion, the wiki and agent tools."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
KnowledgeKind = Literal["term", "metric", "schema", "join_rule", "sql_example", "rule"]


class TableRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    database: str
    schema_name: str
    table: str

    @field_validator("database", "schema_name", "table")
    @classmethod
    def valid_identifier(cls, value: str) -> str:
        if not IDENTIFIER.fullmatch(value):
            raise ValueError("Use a configured database alias and plain SQL identifiers")
        return value

    @property
    def id(self) -> str:
        return f"{self.database.lower()}.{self.schema_name}.{self.table}"

    @classmethod
    def parse(cls, value: str) -> TableRef:
        parts = value.split(".")
        if len(parts) != 3:
            raise ValueError("Table IDs must be database.schema.table")
        return cls(database=parts[0].lower(), schema_name=parts[1], table=parts[2])


class ColumnPair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_$]*$")
    target: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_$]*$")


class JoinRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_table: str
    target_table: str
    column_pairs: list[ColumnPair] = Field(min_length=1, max_length=12)
    cardinality: Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many", "unknown"] = (
        "unknown"
    )
    conditions: str = Field(default="", max_length=2000)
    grain: str = Field(default="", max_length=500)

    @field_validator("source_table", "target_table")
    @classmethod
    def qualified_table(cls, value: str) -> str:
        return TableRef.parse(value).id


class WikiPageDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=120, pattern=r"^[\w-]+$")
    domain: str = Field(min_length=1, max_length=160)
    kind: KnowledgeKind
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=500)
    body_md: str = Field(min_length=1, max_length=24000)
    source_quote: str = Field(min_length=1, max_length=4000)
    table_ids: list[str] = Field(default_factory=list, max_length=40)
    join_rule: JoinRule | None = None

    @field_validator("domain")
    @classmethod
    def domain_path(cls, value: str) -> str:
        parts = [part.strip() for part in value.split("/")]
        if len(parts) > 4 or any(not part or part in {".", ".."} for part in parts):
            raise ValueError("Domain must have one to four non-empty path segments")
        return "/".join(parts)

    @field_validator("table_ids")
    @classmethod
    def qualified_tables(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(TableRef.parse(value).id for value in values))

    @model_validator(mode="after")
    def join_contract(self) -> WikiPageDraft:
        if (self.kind == "join_rule") != (self.join_rule is not None):
            raise ValueError("A join_rule page must contain a structured join rule")
        if self.join_rule:
            self.table_ids = list(
                dict.fromkeys(
                    [
                        *self.table_ids,
                        self.join_rule.source_table,
                        self.join_rule.target_table,
                    ]
                )
            )
        return self


class WikiExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pages: list[WikiPageDraft] = Field(default_factory=list, max_length=60)


class WikiPage(WikiPageDraft):
    id: str
    document_id: str
    revision: int
    source_key: str
    source_line: int
    db_names: list[str]

    def card(self) -> dict:
        """Return discovery metadata only; full Markdown requires an explicit read."""
        return self.model_dump(
            include={
                "id",
                "domain",
                "kind",
                "title",
                "summary",
                "table_ids",
                "document_id",
                "revision",
                "source_key",
                "source_line",
                "db_names",
            }
        )
