"""
Preprocess node for visualization planning.
"""

from __future__ import annotations

from typing import Any

from easysql.llm.agents.viz.schemas import ColumnDataType
from easysql.llm.agents.viz.state import ColumnProfile, SemanticType, VizState

LOW_CARDINALITY_THRESHOLD = 10
HIGH_CARDINALITY_THRESHOLD = 50


def _infer_column_type(values: list[object]) -> ColumnDataType:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "unknown"

    def _is_number(value: object) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return True
        if isinstance(value, str):
            try:
                float(value)
                return True
            except ValueError:
                return False
        return False

    if all(_is_number(v) for v in non_null):
        return "number"

    if all(isinstance(v, bool) for v in non_null):
        return "boolean"

    date_patterns = ("-", "/", "T", ":")
    if all(isinstance(v, str) and any(p in v for p in date_patterns) for v in non_null):
        return "date"

    return "string"


def _infer_semantic_type(
    base_type: ColumnDataType,
    distinct_count: int,
    row_count: int,
) -> SemanticType:
    if base_type == "number" and distinct_count <= LOW_CARDINALITY_THRESHOLD:
        return "categorical_numeric"

    return base_type


def _is_high_cardinality(
    base_type: ColumnDataType,
    distinct_count: int,
    row_count: int,
) -> bool:
    if base_type != "string":
        return False

    if row_count == 0:
        return False

    threshold = max(HIGH_CARDINALITY_THRESHOLD, int(0.2 * row_count))
    return distinct_count >= threshold


def _build_profiles(
    columns: list[str],
    sample_data: list[dict[str, Any]],
    row_count: int,
) -> list[ColumnProfile]:
    profiles: list[ColumnProfile] = []

    for column in columns:
        values = [row.get(column) for row in sample_data]
        distinct = {str(v) for v in values if v is not None}
        distinct_count = len(distinct)
        sample = [str(v) for v in values if v is not None][:5]
        base_type = _infer_column_type(values)

        semantic_type = _infer_semantic_type(base_type, distinct_count, row_count)
        high_cardinality = _is_high_cardinality(base_type, distinct_count, row_count)

        profiles.append(
            {
                "name": column,
                "type": base_type,
                "distinct_count": distinct_count,
                "sample": sample,
                "semantic_type": semantic_type,
                "is_high_cardinality": high_cardinality,
            }
        )

    return profiles


def preprocess_node(state: VizState) -> dict[str, Any]:
    columns = state.get("columns") or []
    sample_data = state.get("sample_data") or []
    row_count = state.get("row_count", 0)
    profiles = _build_profiles(columns, sample_data, row_count)

    column_types = state.get("column_types")
    if column_types is None:
        column_types = [profile["type"] for profile in profiles]

    return {"profile": profiles, "column_types": column_types}
