"""
Visualization planning schemas.

This module defines Pydantic models for LLM-generated chart configurations.
Each field includes descriptions to guide the LLM in producing valid output.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ChartType = Literal[
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
]

ColumnDataType = Literal["number", "string", "date", "boolean", "unknown"]
AggType = Literal["count", "sum", "avg", "min", "max"]
SortDirection = Literal["ascending", "descending", "none"]
LayoutType = Literal["single", "grid", "tabs"]
TimeGrain = Literal["day", "week", "month", "quarter", "year"]

# Chart type selection guide for LLM prompts
CHART_TYPE_GUIDE: dict[str, dict[str, str]] = {
    "bar": {
        "description": "Category comparison",
        "best_for": "Comparing values across categories",
        "data_requirements": "1 categorical + 1 numeric column",
    },
    "horizontal_bar": {
        "description": "Category comparison with long labels",
        "best_for": "Categories with long text names",
        "data_requirements": "1 categorical + 1 numeric column",
    },
    "line": {
        "description": "Time series trends",
        "best_for": "Showing changes over time",
        "data_requirements": "1 date/time + 1 numeric column",
    },
    "area": {
        "description": "Cumulative trends",
        "best_for": "Showing cumulative values over time",
        "data_requirements": "1 date/time + 1 numeric column",
    },
    "pie": {
        "description": "Part-to-whole proportions",
        "best_for": "Showing percentage distribution (≤7 categories)",
        "data_requirements": "1 categorical + 1 numeric column, low cardinality",
    },
    "donut": {
        "description": "Part-to-whole with center metric",
        "best_for": "Proportions with a central KPI",
        "data_requirements": "1 categorical + 1 numeric column, low cardinality",
    },
    "scatter": {
        "description": "Correlation analysis",
        "best_for": "Exploring relationships between two numeric variables",
        "data_requirements": "2 numeric columns",
    },
    "metric_card": {
        "description": "Single KPI display",
        "best_for": "Highlighting a single important number",
        "data_requirements": "1 numeric value",
    },
    "grouped_bar": {
        "description": "Multi-dimensional comparison",
        "best_for": "Comparing across 2 categorical dimensions",
        "data_requirements": "2 categorical + 1 numeric column",
    },
    "stacked_bar": {
        "description": "Part-to-whole by category",
        "best_for": "Showing composition within categories",
        "data_requirements": "2 categorical + 1 numeric column",
    },
    "stacked_area": {
        "description": "Cumulative composition over time",
        "best_for": "Showing how parts contribute to whole over time",
        "data_requirements": "1 date + 1 categorical + 1 numeric column",
    },
}


class BinningConfig(BaseModel):
    """Configuration for binning numeric values into ranges."""

    model_config = ConfigDict(populate_by_name=True)

    field: str = Field(description="Column name to bin")
    bin_size: int | None = Field(
        default=None,
        alias="binSize",
        description="Fixed size for each bin",
    )
    bins: int | None = Field(default=None, description="Number of bins to create")
    alias: str | None = Field(
        default=None,
        description="Display name for the binned column",
    )


class TimeGrainConfig(BaseModel):
    """Configuration for grouping date/time values by time period."""

    model_config = ConfigDict(populate_by_name=True)

    field: str = Field(description="Date/time column name to group")
    grain: TimeGrain = Field(description="Time granularity: day, week, month, quarter, year")
    alias: str | None = Field(
        default=None,
        description="Display name for the time-grouped column",
    )


class ChartIntent(BaseModel):
    """Chart configuration intent for aggregation and rendering.

    This schema guides the LLM to produce valid chart configurations.
    All column references must match exact column names from the data profile.
    """

    model_config = ConfigDict(populate_by_name=True)

    # Required fields
    chart_type: ChartType | str = Field(
        alias="chartType",
        description=(
            "Chart type to render. Choose based on data: "
            "'bar' for category comparison, 'line' for time trends, "
            "'pie' for proportions (≤7 categories), 'scatter' for correlation, "
            "'metric_card' for single KPI."
        ),
    )
    title: str = Field(
        description=(
            "REQUIRED: Clear, descriptive title answering 'What does this chart show?'. "
            "Example: 'Monthly Sales by Region (2024)'. Never leave empty."
        ),
    )

    # Grouping and aggregation
    group_by: str | None = Field(
        default=None,
        alias="groupBy",
        description=(
            "Column name for X-axis or category grouping. "
            "MUST be an exact column name from the data profile. "
            "Required for bar, line, pie, area charts."
        ),
    )
    agg: AggType | str | None = Field(
        default=None,
        description=(
            "Aggregation function: 'count' for frequency, 'sum' for totals, "
            "'avg' for averages, 'min'/'max' for extremes. "
            "For sum/avg/min/max, valueField MUST be a numeric column."
        ),
    )
    value_field: str | None = Field(
        default=None,
        alias="valueField",
        description=(
            "Column name for Y-axis or measure values. "
            "MUST be a numeric column for sum/avg/min/max aggregation. "
            "Can be omitted when using 'count' aggregation."
        ),
    )
    series_field: str | None = Field(
        default=None,
        alias="seriesField",
        description="Column for grouping into multiple series (for grouped/stacked charts)",
    )

    # Display options
    label: str | None = Field(
        default=None,
        description="Short label for the chart (used in tabs or legends)",
    )
    top_n: int | None = Field(
        default=None,
        alias="topN",
        description="Limit display to top N items (must be positive integer)",
    )
    sort: SortDirection | str | None = Field(
        default=None,
        description="Sort order: 'ascending', 'descending', or 'none'",
    )

    # Axis configuration
    x_field: str | None = Field(
        default=None,
        alias="xField",
        description="Explicit X-axis column (overrides groupBy if set)",
    )
    y_field: str | None = Field(
        default=None,
        alias="yField",
        description="Explicit Y-axis column (overrides valueField if set)",
    )
    x_axis_label: str | None = Field(
        default=None,
        alias="xAxisLabel",
        description="Human-readable label for X-axis",
    )
    y_axis_label: str | None = Field(
        default=None,
        alias="yAxisLabel",
        description="Human-readable label for Y-axis",
    )
    x_unit: str | None = Field(
        default=None,
        alias="xUnit",
        description="Unit for X-axis values (e.g., 'days', 'USD')",
    )
    y_unit: str | None = Field(
        default=None,
        alias="yUnit",
        description="Unit for Y-axis values (e.g., '$', '%', 'units')",
    )

    # Additional options
    show_percentage: bool | None = Field(
        default=None,
        alias="showPercentage",
        description="Show percentage labels (useful for pie/donut charts)",
    )
    binning: BinningConfig | None = Field(
        default=None,
        description="Configuration for binning numeric values into ranges",
    )
    time_grain: TimeGrainConfig | TimeGrain | str | None = Field(
        default=None,
        alias="timeGrain",
        description="Time granularity for date grouping: 'day', 'week', 'month', 'quarter', 'year'",
    )


class VizPlan(BaseModel):
    """Complete visualization plan containing one or more chart intents."""

    model_config = ConfigDict(populate_by_name=True)

    suitable: bool = Field(
        default=True,
        description="Whether the data is suitable for visualization",
    )
    charts: list[ChartIntent] = Field(
        default_factory=list,
        description="List of chart configurations to render",
    )
    layout: LayoutType | None = Field(
        default=None,
        description="Layout for multiple charts: 'single', 'grid', or 'tabs'",
    )
    narrative: list[str] | None = Field(
        default=None,
        description="Explanatory text to accompany the visualization",
    )
    reasoning: str | None = Field(
        default=None,
        description="Explanation of why this chart type was chosen",
    )
