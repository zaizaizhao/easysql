"""
Base model definitions for EasySql.

Provides common base classes and mixins for all data models.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict, Field


class BaseModel(PydanticBaseModel):
    """
    Base model with common configuration for all EasySql models.

    Features:
    - Immutable by default (frozen=True can be enabled per model)
    - JSON serialization support
    - Validation on assignment
    """

    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary."""
        return self.model_dump(mode="json", exclude_none=True)

    def to_json(self) -> str:
        """Convert model to JSON string."""
        return self.model_dump_json(exclude_none=True)


class TimestampMixin(BaseModel):
    """Mixin for models with timestamp tracking."""

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime | None = None


class IdentifiableMixin(BaseModel):
    """Mixin for models with unique identifiers."""

    id: str = Field(..., description="Unique identifier")

    def get_neo4j_id(self) -> str:
        """Get ID suitable for Neo4j node identification."""
        return self.id.replace(".", "_").replace("-", "_")
