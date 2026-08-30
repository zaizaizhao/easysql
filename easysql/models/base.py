"""
Base model definitions for EasySql.

Provides the common base class for all data models.
"""

from typing import Any

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict


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
