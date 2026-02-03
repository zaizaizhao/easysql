"""
Prompt templates for visualization planning.
"""

from __future__ import annotations

import json
from typing import Any

VIZ_SYSTEM_PROMPT = """\
You are a data visualization planning agent.
Your task is to generate chart configurations based on the data profile and user question.

## Chart Type Selection Guide

| Chart Type | Best For | Data Requirements |
|------------|----------|-------------------|
| bar | Comparing categories | 1 categorical + 1 numeric column |
| horizontal_bar | Categories with long labels | Same as bar, for long text |
| line | Time series trends | 1 date/time + 1 numeric column |
| area | Cumulative trends | 1 date/time + 1 numeric column |
| pie | Proportions (≤7 categories) | 1 categorical + 1 numeric, low cardinality |
| donut | Proportions with center metric | Same as pie |
| scatter | Correlation analysis | 2 numeric columns |
| metric_card | Single KPI value | 1 numeric value |
| grouped_bar | Compare across 2 dimensions | 2 categorical + 1 numeric |
| stacked_bar | Part-to-whole by category | 2 categorical + 1 numeric |
| stacked_area | Composition over time | 1 date + 1 categorical + 1 numeric |

## JSON Field Names (MUST use these exact names)

- `chartType` (NOT "type") - chart type to render
- `title` - chart title (REQUIRED)
- `groupBy` - column for X-axis grouping
- `valueField` - column for Y-axis values
- `agg` - aggregation function

## STRICT RULES

1. **title is REQUIRED for every chart**: Generate a clear, descriptive title.
   - Good: "Monthly Sales by Region", "Top 10 Products by Revenue"
   - Bad: "Chart", "Data", or empty

2. **Use EXACT column names**: Only use column names from the profile.

3. **Match aggregation to data type**:
   - sum/avg/min/max → valueField MUST be a numeric column
   - count → valueField can be omitted

4. **Avoid pie/donut when**:
   - More than 7 categories (use bar instead)
   - Comparing across time (use line instead)

5. **Use binning for continuous distributions** (age, price, etc.)

6. **Use timeGrain for date columns**: { "field": "date_col", "grain": "month" }

Output ONLY valid JSON matching the VizPlan schema. Do not explain.
"""

ERROR_CORRECTION_PROMPT = """\
Your previous chart plan failed validation with the following error:

{error_message}

Please correct the plan and try again. Do NOT repeat the same mistake.

Common fixes:
- Use `chartType` field (NOT "type") for chart type
- Ensure groupBy and valueField are EXACT column names from the profile
- For sum/avg/min/max aggregation, valueField must be a numeric column
- For pie/donut/bar charts, groupBy is required
- title is REQUIRED for every chart - never leave it empty
- topN must be a positive integer if specified

Return a corrected VizPlan JSON only.
"""


def _format_profile_table(profile: list[dict[str, Any]]) -> str:
    """Format column profile as a markdown table for the prompt."""
    if not profile:
        return "(no columns)"

    lines = [
        "| Column | Type | Distinct | High Cardinality | Sample Values |",
        "|--------|------|----------|------------------|---------------|",
    ]

    for col in profile:
        name = col.get("name", "")
        col_type = col.get("type", "unknown")
        distinct = col.get("distinct_count", "?")
        high_card = "Yes" if col.get("is_high_cardinality") else ""
        samples = col.get("sample", [])
        sample_str = ", ".join(str(s) for s in samples[:3])
        if len(sample_str) > 40:
            sample_str = sample_str[:37] + "..."
        lines.append(f"| {name} | {col_type} | {distinct} | {high_card} | {sample_str} |")

    return "\n".join(lines)


def build_viz_user_prompt(
    *,
    question: str | None,
    sql: str | None,
    profile_json: str,
    sample_json: str,
    row_count: int,
    previous_plan_json: str | None,
) -> str:
    """Build the user prompt for visualization planning."""
    try:
        profile_data = json.loads(profile_json) if profile_json else []
    except json.JSONDecodeError:
        profile_data = []

    profile_table = _format_profile_table(profile_data)

    lines = [
        "## User Question",
        question or "(no specific question)",
        "",
        "## SQL Query",
        f"```sql\n{sql or '(none)'}\n```",
        "",
        f"## Data Summary: {row_count} rows",
        "",
        "## Column Profile",
        profile_table,
        "",
        "## Sample Data (first rows)",
        f"```json\n{sample_json}\n```",
    ]

    if previous_plan_json:
        lines.extend(
            [
                "",
                "## Previous Plan (for refinement)",
                f"```json\n{previous_plan_json}\n```",
            ]
        )

    lines.extend(
        [
            "",
            "## Your Task",
            "Generate a VizPlan with 1-3 chart suggestions. For EACH chart:",
            "1. A **clear title** describing what the chart shows (REQUIRED)",
            "2. The **best chart type** for this data",
            "3. Correct **groupBy** and **valueField** using exact column names",
            "4. Appropriate **aggregation** (count, sum, avg, min, max)",
            "5. **reasoning** explaining your chart type choice",
        ]
    )

    return "\n".join(lines)


def build_error_correction_prompt(error_message: str) -> str:
    """Build the error correction prompt for retry attempts."""
    return ERROR_CORRECTION_PROMPT.format(error_message=error_message)
