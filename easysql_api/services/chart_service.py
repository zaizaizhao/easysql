"""
Chart recommendation service.

Runs the visualization planning LangGraph agent and maps intent to chart config.
"""

from __future__ import annotations

from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from easysql.llm.agent import get_langfuse_callbacks
from easysql.llm.agents.viz.agent import build_viz_graph
from easysql.llm.agents.viz.schemas import (
    BinningConfig,
    ChartIntent,
    ChartType,
    SortDirection,
    TimeGrainConfig,
    VizPlan,
)
from easysql.llm.agents.viz.state import VizState
from easysql_api.models.chart import ChartConfig, ChartRecommendRequest, ChartRecommendResponse
from easysql_api.services.chart_aggregation import AGG_VALUE_ALIAS, aggregate_chart_data


class ChartService:
    def __init__(self) -> None:
        self._graph: Any = None
        self._callbacks: list[Any] | None = None

    @property
    def graph(self) -> Any:
        if self._graph is None:
            self._graph = build_viz_graph()
        return self._graph

    @property
    def callbacks(self) -> list[Any]:
        if self._callbacks is None:
            self._callbacks = get_langfuse_callbacks()
        return self._callbacks

    async def recommend(self, request: ChartRecommendRequest) -> ChartRecommendResponse:
        if request.selected_intent is not None:
            selected_intent = request.selected_intent
            chart_config = self._intent_to_config(selected_intent)
            data_source = request.data or request.sample_data
            selected_chart_data = aggregate_chart_data(data_source, selected_intent)
            suitable = bool(chart_config and selected_chart_data)
            return ChartRecommendResponse(
                suitable=suitable,
                config=chart_config,
                chartData=selected_chart_data,
                intent=selected_intent,
                reasoning=None,
                plan=request.previous_plan,
                error=None if suitable else "Selected intent not suitable for data",
            )

        input_state: VizState = {
            "question": request.question,
            "sql": request.sql,
            "columns": request.columns,
            "column_types": request.column_types,
            "sample_data": request.sample_data,
            "row_count": request.row_count,
            "previous_plan": request.previous_plan,
        }

        config: RunnableConfig = {}
        if self.callbacks:
            config["callbacks"] = self.callbacks

        result = await self.graph.ainvoke(input_state, config or None)
        plan = self._coerce_plan(result.get("plan"))
        errors = result.get("errors") or []
        fallback_applied = bool(result.get("fallback"))

        if plan is None:
            error_msg = errors[0] if errors else "Chart plan generation failed"
            return ChartRecommendResponse(suitable=False, error=error_msg)

        if fallback_applied:
            error_msg = errors[0] if errors else "No suitable chart suggestions"
            return ChartRecommendResponse(suitable=False, error=error_msg)

        if request.plan_only:
            suitable = bool(plan.suitable and plan.charts)
            reasoning = plan.reasoning
            if errors and not reasoning:
                reasoning = "; ".join(errors[:3])
            return ChartRecommendResponse(
                suitable=suitable,
                config=None,
                chartData=None,
                reasoning=reasoning,
                intent=None,
                plan=plan,
                error=None if suitable else (errors[0] if errors else None),
            )

        intent: ChartIntent | None = plan.charts[0] if plan.charts else None
        chart_config = self._intent_to_config(intent) if intent else None
        data_source = request.data if request.data is not None else request.sample_data
        chart_data: list[dict[str, Any]] | None = (
            aggregate_chart_data(data_source, intent) if intent else None
        )

        suitable = bool(plan.suitable and plan.charts)
        reasoning = plan.reasoning
        if errors and not reasoning:
            reasoning = "; ".join(errors[:3])

        return ChartRecommendResponse(
            suitable=suitable,
            config=chart_config,
            chartData=chart_data,
            reasoning=reasoning,
            intent=intent,
            plan=plan,
            error=None if suitable else (errors[0] if errors else None),
        )

    @staticmethod
    def _intent_to_config(intent: ChartIntent | None) -> ChartConfig | None:
        if intent is None:
            return None
        chart_type = _normalize_chart_type(intent.chart_type)
        if chart_type is None:
            return None
        sort = _normalize_sort(intent.sort)
        group_by = intent.group_by
        if isinstance(intent.binning, BinningConfig):
            bin_alias = intent.binning.alias or f"{intent.binning.field}_bin"
            if group_by is None or group_by == intent.binning.field:
                group_by = bin_alias
        if isinstance(intent.time_grain, TimeGrainConfig):
            grain_alias = (
                intent.time_grain.alias or f"{intent.time_grain.field}_{intent.time_grain.grain}"
            )
            if group_by is None or group_by == intent.time_grain.field:
                group_by = grain_alias

        if chart_type in {
            "bar",
            "line",
            "area",
            "grouped_bar",
            "stacked_bar",
            "stacked_area",
        }:
            if not group_by and isinstance(intent.binning, BinningConfig):
                group_by = intent.binning.alias or f"{intent.binning.field}_bin"
            if not group_by and isinstance(intent.time_grain, TimeGrainConfig):
                group_by = (
                    intent.time_grain.alias
                    or f"{intent.time_grain.field}_{intent.time_grain.grain}"
                )
            if not group_by:
                return None
            x_axis_label = _format_axis_label(intent.x_axis_label, intent.x_unit)
            y_axis_label = _format_axis_label(intent.y_axis_label, intent.y_unit)
            return ChartConfig(
                chartType=chart_type,
                title=intent.title,
                xField=group_by,
                yField=AGG_VALUE_ALIAS,
                seriesField=intent.series_field,
                sort=sort,
                stacked=chart_type in {"stacked_bar", "stacked_area"},
                xAxisLabel=x_axis_label,
                yAxisLabel=y_axis_label,
            )

        if chart_type == "horizontal_bar":
            if not group_by and isinstance(intent.binning, BinningConfig):
                group_by = intent.binning.alias or f"{intent.binning.field}_bin"
            if not group_by and isinstance(intent.time_grain, TimeGrainConfig):
                group_by = (
                    intent.time_grain.alias
                    or f"{intent.time_grain.field}_{intent.time_grain.grain}"
                )
            if not group_by:
                return None
            x_axis_label = _format_axis_label(intent.y_axis_label, intent.y_unit)
            y_axis_label = _format_axis_label(intent.x_axis_label, intent.x_unit)
            return ChartConfig(
                chartType=chart_type,
                title=intent.title,
                xField=AGG_VALUE_ALIAS,
                yField=group_by,
                seriesField=intent.series_field,
                sort=sort,
                xAxisLabel=x_axis_label,
                yAxisLabel=y_axis_label,
            )

        if chart_type in {"pie", "donut"}:
            if not group_by and isinstance(intent.binning, BinningConfig):
                group_by = intent.binning.alias or f"{intent.binning.field}_bin"
            if not group_by and isinstance(intent.time_grain, TimeGrainConfig):
                group_by = (
                    intent.time_grain.alias
                    or f"{intent.time_grain.field}_{intent.time_grain.grain}"
                )
            if not group_by:
                return None
            return ChartConfig(
                chartType=chart_type,
                title=intent.title,
                angleField=AGG_VALUE_ALIAS,
                colorField=group_by,
                showLegend=True,
                showLabels=True,
                showPercentage=(
                    intent.show_percentage if intent.show_percentage is not None else True
                ),
            )

        if chart_type == "metric_card":
            return ChartConfig(
                chartType=chart_type,
                title=intent.title,
                valueField=AGG_VALUE_ALIAS,
                labelField=intent.group_by,
            )

        if chart_type == "scatter":
            if not intent.x_field or not intent.y_field:
                return None
            x_axis_label = _format_axis_label(intent.x_axis_label, intent.x_unit)
            y_axis_label = _format_axis_label(intent.y_axis_label, intent.y_unit)
            return ChartConfig(
                chartType=chart_type,
                title=intent.title,
                xField=intent.x_field,
                yField=intent.y_field,
                seriesField=intent.series_field,
                xAxisLabel=x_axis_label,
                yAxisLabel=y_axis_label,
            )

        return None

    @staticmethod
    def _coerce_plan(raw_plan: Any) -> VizPlan | None:
        if isinstance(raw_plan, VizPlan):
            return raw_plan
        if isinstance(raw_plan, dict):
            try:
                return VizPlan.model_validate(raw_plan)
            except ValidationError:
                return None
        return None


def _format_axis_label(label: str | None, unit: str | None) -> str | None:
    if not label:
        return None
    if unit:
        if unit in label:
            return label
        return f"{label} ({unit})"
    return label


def _normalize_chart_type(raw_type: ChartType | str) -> ChartType | None:
    if raw_type in {
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
    }:
        return cast(ChartType, raw_type)
    return None


def _normalize_sort(raw_sort: SortDirection | str | None) -> SortDirection | None:
    if raw_sort in {"ascending", "descending", "none"}:
        return cast(SortDirection, raw_sort)
    return None


_default_service: ChartService | None = None


def get_chart_service() -> ChartService:
    global _default_service
    if _default_service is None:
        _default_service = ChartService()
    return _default_service


def reset_chart_service_callbacks() -> None:
    global _default_service
    if _default_service is not None:
        _default_service._callbacks = None


def warm_chart_service_callbacks() -> None:
    global _default_service
    if _default_service is not None:
        _ = _default_service.callbacks
