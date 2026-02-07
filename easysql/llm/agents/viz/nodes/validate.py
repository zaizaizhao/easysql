"""
Validate and normalize visualization plan with intelligent fallback.
"""

from __future__ import annotations

from typing import Any

from easysql.llm.agents.viz.schemas import (
    AggType,
    ChartIntent,
    ChartType,
    ColumnDataType,
    TimeGrainConfig,
    VizPlan,
)
from easysql.llm.agents.viz.state import ColumnProfile, VizState

_NUMERIC_REQUIRED_AGGS: set[AggType] = {"sum", "avg", "min", "max"}
_ALLOWED_CHART_TYPES: set[str] = {
    "bar",
    "line",
    "pie",
    "scatter",
    "area",
    "horizontal_bar",
    "donut",
    "grouped_bar",
    "stacked_bar",
    "stacked_area",
    "metric_card",
}
_ALLOWED_AGGS: set[str] = {"count", "sum", "avg", "min", "max"}
_ALLOWED_SORT: set[str] = {"ascending", "descending", "none"}
_AXIS_LABEL_REQUIRED_TYPES: set[str] = {
    "bar",
    "line",
    "area",
    "horizontal_bar",
    "grouped_bar",
    "stacked_bar",
    "stacked_area",
    "scatter",
}

PIE_MAX_CATEGORIES = 7
TOP_N_DEFAULT = 10


def _build_type_map(
    columns: list[str],
    column_types: list[ColumnDataType],
) -> dict[str, ColumnDataType]:
    return {
        column: column_types[idx] if idx < len(column_types) else "unknown"
        for idx, column in enumerate(columns)
    }


def _humanize_column_name(name: str) -> str:
    """Convert column_name or column-name to Column Name."""
    return name.replace("_", " ").replace("-", " ").title()


def _generate_fallback_title(
    chart_type: str,
    x_col: str | None,
    y_col: str | None,
    agg: str | None,
    question: str | None,
) -> str:
    if question and len(question) <= 60:
        return question.strip()

    if question and len(question) > 60:
        return question[:57].strip() + "..."

    if y_col and x_col:
        y_name = _humanize_column_name(y_col)
        x_name = _humanize_column_name(x_col)
        if agg and agg != "count":
            return f"{agg.upper()} of {y_name} by {x_name}"
        return f"{y_name} by {x_name}"

    if y_col:
        y_name = _humanize_column_name(y_col)
        if chart_type == "metric_card":
            return f"Total {y_name}"
        return f"{y_name} Distribution"

    if x_col:
        x_name = _humanize_column_name(x_col)
        return f"{x_name} Count"

    return "Data Overview"


def _enforce_pie_topn(intent: ChartIntent, profile: list[ColumnProfile] | None) -> None:
    if str(intent.chart_type) not in {"pie", "donut"}:
        return
    if not intent.group_by or not profile:
        return
    column_profile = next((col for col in profile if col["name"] == intent.group_by), None)
    if not column_profile:
        return
    distinct_count = column_profile.get("distinct_count")
    if distinct_count is None or distinct_count <= PIE_MAX_CATEGORIES:
        return
    if intent.top_n is None or intent.top_n > PIE_MAX_CATEGORIES:
        intent.top_n = PIE_MAX_CATEGORIES


def _needs_group_by(intent: ChartIntent) -> bool:
    if intent.chart_type in {"metric_card", "scatter"}:
        return False
    if intent.binning or isinstance(intent.time_grain, TimeGrainConfig):
        return False
    return True


def _select_chart_type_for_data(
    profile: list[ColumnProfile],
    string_cols: list[str],
    numeric_cols: list[str],
    date_cols: list[str],
) -> ChartType:
    if date_cols and numeric_cols:
        return "line"

    if string_cols and numeric_cols:
        col_profile = next((p for p in profile if p["name"] == string_cols[0]), None)
        distinct_count = col_profile["distinct_count"] if col_profile else 10

        if distinct_count <= PIE_MAX_CATEGORIES:
            return "pie"
        if distinct_count > 20:
            return "horizontal_bar"
        return "bar"

    if string_cols:
        return "bar"

    if len(numeric_cols) >= 2:
        return "scatter"

    if numeric_cols:
        return "metric_card"

    return "bar"


def _fallback_plan(
    *,
    columns: list[str],
    column_types: list[ColumnDataType],
    row_count: int,
    question: str | None = None,
    profile: list[ColumnProfile] | None = None,
) -> VizPlan:
    type_map = _build_type_map(columns, column_types)
    profile = profile or []

    numeric_cols = [col for col in columns if type_map.get(col) == "number"]
    string_cols = [col for col in columns if type_map.get(col) == "string"]
    date_cols = [col for col in columns if type_map.get(col) == "date"]

    chart_type = _select_chart_type_for_data(profile, string_cols, numeric_cols, date_cols)

    if chart_type == "line" and date_cols and numeric_cols:
        x_col, y_col = date_cols[0], numeric_cols[0]
        title = _generate_fallback_title("line", x_col, y_col, "sum", question)
        intent = ChartIntent(
            chartType=chart_type,
            title=title,
            groupBy=x_col,
            agg="sum",
            valueField=y_col,
        )
        return VizPlan(
            suitable=True,
            charts=[intent],
            layout="single",
            reasoning=f"Fallback: time series {x_col} vs {y_col}",
        )

    if chart_type in {"bar", "horizontal_bar", "pie"} and string_cols and numeric_cols:
        x_col, y_col = string_cols[0], numeric_cols[0]
        col_profile = next((p for p in profile if p["name"] == x_col), None)
        distinct_count = col_profile["distinct_count"] if col_profile else 10

        top_n = TOP_N_DEFAULT if distinct_count > TOP_N_DEFAULT else None
        title = _generate_fallback_title(chart_type, x_col, y_col, "sum", question)

        intent = ChartIntent(
            chartType=chart_type,
            title=title,
            groupBy=x_col,
            agg="sum",
            valueField=y_col,
            sort="descending",
            topN=top_n,
        )
        return VizPlan(
            suitable=True,
            charts=[intent],
            layout="single",
            reasoning=f"Fallback: {chart_type} chart ({distinct_count} categories)",
        )

    if chart_type == "bar" and string_cols:
        x_col = string_cols[0]
        title = _generate_fallback_title("bar", x_col, None, "count", question)
        intent = ChartIntent(
            chartType="bar",
            title=title,
            groupBy=x_col,
            agg="count",
            sort="descending",
        )
        return VizPlan(
            suitable=True,
            charts=[intent],
            layout="single",
            reasoning="Fallback: bar chart with count",
        )

    if chart_type == "scatter" and len(numeric_cols) >= 2:
        x_col, y_col = numeric_cols[0], numeric_cols[1]
        title = _generate_fallback_title("scatter", x_col, y_col, None, question)
        intent = ChartIntent(
            chartType="scatter",
            title=title,
            xField=x_col,
            yField=y_col,
        )
        return VizPlan(
            suitable=True,
            charts=[intent],
            layout="single",
            reasoning=f"Fallback: scatter plot {x_col} vs {y_col}",
        )

    if chart_type == "metric_card" and numeric_cols:
        y_col = numeric_cols[0]
        title = _generate_fallback_title("metric_card", None, y_col, "sum", question)
        intent = ChartIntent(
            chartType="metric_card",
            title=title,
            valueField=y_col,
            agg="sum",
        )
        return VizPlan(
            suitable=True,
            charts=[intent],
            layout="single",
            reasoning="Fallback: metric card",
        )

    return VizPlan(
        suitable=False,
        charts=[],
        layout="single",
        reasoning="No suitable columns for visualization",
    )


def _validate_intent(
    intent: ChartIntent,
    columns: list[str],
    type_map: dict[str, ColumnDataType],
) -> list[str]:
    errors: list[str] = []
    chart_type = str(intent.chart_type)

    if not intent.group_by:
        if chart_type == "horizontal_bar" and intent.y_field:
            intent.group_by = intent.y_field
        elif chart_type in {
            "bar",
            "line",
            "area",
            "grouped_bar",
            "stacked_bar",
            "stacked_area",
            "pie",
            "donut",
        } and intent.x_field:
            intent.group_by = intent.x_field

    if chart_type not in _ALLOWED_CHART_TYPES:
        errors.append(f"chartType invalid: {intent.chart_type}")

    if not intent.title:
        errors.append("title is required")

    if chart_type in _AXIS_LABEL_REQUIRED_TYPES:
        if not intent.x_axis_label:
            errors.append("xAxisLabel is required for axis charts")
        if not intent.y_axis_label:
            errors.append("yAxisLabel is required for axis charts")

    if intent.agg and str(intent.agg) not in _ALLOWED_AGGS:
        errors.append(f"agg invalid: {intent.agg}")

    if intent.sort and str(intent.sort) not in _ALLOWED_SORT:
        errors.append(f"sort invalid: {intent.sort}")

    if intent.group_by and intent.group_by not in columns:
        derived_ok = False
        if intent.binning:
            alias = intent.binning.alias or f"{intent.binning.field}_bin"
            derived_ok = intent.group_by == alias
        if isinstance(intent.time_grain, TimeGrainConfig) and not derived_ok:
            alias = (
                intent.time_grain.alias or f"{intent.time_grain.field}_{intent.time_grain.grain}"
            )
            derived_ok = intent.group_by == alias
        if not derived_ok:
            errors.append(f"groupBy not found: {intent.group_by}")

    if _needs_group_by(intent) and not intent.group_by:
        errors.append("groupBy is required for this chartType")

    if intent.value_field and intent.value_field not in columns:
        errors.append(f"valueField not found: {intent.value_field}")

    if intent.series_field and intent.series_field not in columns:
        errors.append(f"seriesField not found: {intent.series_field}")

    if chart_type == "scatter":
        if not intent.x_field or not intent.y_field:
            errors.append("scatter requires xField and yField")
        if intent.x_field and intent.x_field not in columns:
            errors.append(f"xField not found: {intent.x_field}")
        if intent.y_field and intent.y_field not in columns:
            errors.append(f"yField not found: {intent.y_field}")

    if intent.agg in _NUMERIC_REQUIRED_AGGS:
        if not intent.value_field:
            errors.append("valueField required for numeric aggregation")
        elif type_map.get(intent.value_field) != "number":
            errors.append("valueField must be numeric for selected aggregation")

    if intent.binning:
        if intent.binning.field not in columns:
            errors.append(f"binning field not found: {intent.binning.field}")
        if intent.binning.bin_size is not None and intent.binning.bin_size <= 0:
            errors.append("binSize must be positive")
        if intent.binning.bins is not None and intent.binning.bins <= 0:
            errors.append("bins must be positive")

    if intent.time_grain is not None and not isinstance(intent.time_grain, TimeGrainConfig):
        errors.append("timeGrain must be an object with field and grain")
    if isinstance(intent.time_grain, TimeGrainConfig) and intent.time_grain.field not in columns:
        errors.append(f"timeGrain field not found: {intent.time_grain.field}")

    if intent.top_n is not None and intent.top_n <= 0:
        errors.append("topN must be positive")

    return errors


def validate_plan_node(state: VizState) -> dict[str, Any]:
    columns = state.get("columns") or []
    column_types = state.get("column_types") or ["unknown"] * len(columns)
    type_map = _build_type_map(columns, column_types)
    question = state.get("question")
    profile = state.get("profile")

    plan = state.get("plan")
    errors: list[str] = []

    if plan is None or not plan.charts:
        plan = _fallback_plan(
            columns=columns,
            column_types=column_types,
            row_count=state.get("row_count", 0),
            question=question,
            profile=profile,
        )
        errors.append("No plan provided; fallback applied.")
        return {"plan": plan, "errors": errors, "fallback": True}

    valid_charts: list[ChartIntent] = []
    for intent in plan.charts:
        intent_errors = _validate_intent(intent, columns, type_map)
        if intent_errors:
            errors.extend(intent_errors)
            continue

        _enforce_pie_topn(intent, profile)
        valid_charts.append(intent)

    if not valid_charts:
        fallback = _fallback_plan(
            columns=columns,
            column_types=column_types,
            row_count=state.get("row_count", 0),
            question=question,
            profile=profile,
        )
        errors.append("No valid charts after validation; fallback applied.")
        return {"plan": fallback, "errors": errors, "fallback": True}

    plan.charts = valid_charts
    if errors:
        plan.reasoning = plan.reasoning or "; ".join(errors[:3])

    return {"plan": plan, "errors": errors or None, "fallback": False}
