from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from easysql.llm.agents.viz.schemas import (
    ChartIntent,
    ChartType,
    ColumnDataType,
    SortDirection,
    VizPlan,
)

LegendPosition = Literal["top", "bottom", "left", "right", "none"]


class ChartConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    chart_type: ChartType = Field(alias="chartType")
    title: str | None = None
    x_field: str | None = Field(default=None, alias="xField")
    y_field: str | None = Field(default=None, alias="yField")
    series_field: str | None = Field(default=None, alias="seriesField")
    angle_field: str | None = Field(default=None, alias="angleField")
    color_field: str | None = Field(default=None, alias="colorField")
    value_field: str | None = Field(default=None, alias="valueField")
    label_field: str | None = Field(default=None, alias="labelField")
    sort: SortDirection | None = None
    show_legend: bool | None = Field(default=None, alias="showLegend")
    legend_position: LegendPosition | None = Field(default=None, alias="legendPosition")
    show_labels: bool | None = Field(default=None, alias="showLabels")
    smooth: bool | None = None
    stacked: bool | None = None
    colors: list[str] | None = None
    x_axis_label: str | None = Field(default=None, alias="xAxisLabel")
    y_axis_label: str | None = Field(default=None, alias="yAxisLabel")
    value_format: str | None = Field(default=None, alias="valueFormat")
    show_percentage: bool | None = Field(default=None, alias="showPercentage")


class ChartRecommendRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str | None = Field(default=None, alias="sessionId")
    turn_id: str | None = Field(default=None, alias="turnId")
    question: str | None = None
    sql: str | None = None
    columns: list[str]
    column_types: list[ColumnDataType] | None = Field(default=None, alias="columnTypes")
    data: list[dict[str, Any]] | None = Field(default=None, alias="data")
    sample_data: list[dict[str, Any]] = Field(alias="sampleData")
    row_count: int = Field(alias="rowCount")
    previous_plan: VizPlan | None = Field(default=None, alias="previousPlan")
    selected_intent: ChartIntent | None = Field(default=None, alias="selectedIntent")
    chart_instruction: str | None = Field(default=None, alias="chartInstruction")
    plan_only: bool = Field(default=False, alias="planOnly")
    force_refresh: bool = Field(default=False, alias="forceRefresh")


class ChartRecommendResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    suitable: bool
    config: ChartConfig | None = None
    chart_data: list[dict[str, Any]] | None = Field(default=None, alias="chartData")
    reasoning: str | None = None
    alternatives: list[ChartConfig] | None = None
    error: str | None = None
    intent: ChartIntent | None = None
    plan: VizPlan | None = None
