"""
State definition for visualization planning agent.
"""

from typing import Any, Literal, TypedDict

from typing_extensions import NotRequired

from easysql.llm.agents.viz.schemas import ColumnDataType, VizPlan

SemanticType = Literal[
    "number",
    "string",
    "date",
    "boolean",
    "unknown",
    "categorical_numeric",
]


class ColumnProfile(TypedDict):
    name: str
    type: ColumnDataType
    distinct_count: int
    sample: list[str]
    semantic_type: NotRequired[SemanticType]
    is_high_cardinality: NotRequired[bool]


class VizState(TypedDict):
    question: str | None
    sql: str | None
    chart_instruction: NotRequired[str | None]
    columns: list[str]
    column_types: list[ColumnDataType] | None
    sample_data: list[dict[str, Any]]
    row_count: int
    previous_plan: NotRequired[VizPlan | None]
    profile: NotRequired[list[ColumnProfile] | None]
    plan: NotRequired[VizPlan | None]
    errors: NotRequired[list[str] | None]
