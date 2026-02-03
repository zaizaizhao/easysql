"""
Chart data aggregation helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from easysql.llm.agents.viz.schemas import (
    AggType,
    BinningConfig,
    ChartIntent,
    TimeGrain,
    TimeGrainConfig,
)

AGG_VALUE_ALIAS = "__value"


@dataclass
class _AggState:
    total: float = 0.0
    count: int = 0
    min_value: float | None = None
    max_value: float | None = None

    def update(self, value: float) -> None:
        self.total += value
        self.count += 1
        if self.min_value is None or value < self.min_value:
            self.min_value = value
        if self.max_value is None or value > self.max_value:
            self.max_value = value


def _coerce_numeric(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _compute_agg(state: _AggState, agg: AggType) -> float | int:
    if agg == "count":
        return state.count
    if agg == "sum":
        return state.total
    if agg == "avg":
        return state.total / state.count if state.count else 0.0
    if agg == "min":
        return state.min_value if state.min_value is not None else 0.0
    if agg == "max":
        return state.max_value if state.max_value is not None else 0.0
    return state.total


def aggregate_chart_data(
    rows: list[dict[str, Any]],
    intent: ChartIntent | None,
) -> list[dict[str, Any]]:
    if not rows or intent is None:
        return []

    if str(intent.chart_type) == "scatter":
        return _aggregate_scatter(rows, intent)

    processed_rows, group_by = _apply_transforms(rows, intent)
    if not processed_rows:
        return []

    agg: AggType = intent.agg or ("count" if not intent.value_field else "sum")
    series_field = intent.series_field

    if str(intent.chart_type) == "metric_card":
        return _aggregate_metric_card(processed_rows, intent, agg, group_by)

    if not group_by:
        return []

    grouped: dict[tuple[str, str | None], _AggState] = {}

    for row in processed_rows:
        group_value = row.get(group_by)
        group_key = "NULL" if group_value is None else str(group_value)
        series_key: str | None = None
        if series_field:
            series_value = row.get(series_field)
            series_key = "NULL" if series_value is None else str(series_value)

        key = (group_key, series_key)
        state = grouped.setdefault(key, _AggState())

        if agg == "count":
            state.update(1.0)
            continue

        numeric = _coerce_numeric(row.get(intent.value_field or ""))
        if numeric is None:
            continue
        state.update(numeric)

    aggregated: list[dict[str, Any]] = []
    for (group_key, series_key), state in grouped.items():
        value = _compute_agg(state, agg)
        item: dict[str, Any] = {group_by: group_key, AGG_VALUE_ALIAS: value}
        if series_field and series_key is not None:
            item[series_field] = series_key
        aggregated.append(item)

    aggregated = _apply_topn_and_sort(aggregated, intent, group_by)
    return aggregated


def _aggregate_metric_card(
    rows: list[dict[str, Any]],
    intent: ChartIntent,
    agg: AggType,
    group_by: str | None,
) -> list[dict[str, Any]]:
    if not group_by:
        state = _AggState()
        for row in rows:
            if agg == "count":
                state.update(1.0)
                continue
            numeric = _coerce_numeric(row.get(intent.value_field or ""))
            if numeric is None:
                continue
            state.update(numeric)
        return [{AGG_VALUE_ALIAS: _compute_agg(state, agg)}]

    grouped: dict[str, _AggState] = {}
    for row in rows:
        group_value = row.get(group_by)
        group_key = "NULL" if group_value is None else str(group_value)
        state = grouped.setdefault(group_key, _AggState())
        if agg == "count":
            state.update(1.0)
            continue
        numeric = _coerce_numeric(row.get(intent.value_field or ""))
        if numeric is None:
            continue
        state.update(numeric)

    if not grouped:
        return []

    best_group = max(grouped.items(), key=lambda item: _compute_agg(item[1], agg))
    return [{group_by: best_group[0], AGG_VALUE_ALIAS: _compute_agg(best_group[1], agg)}]


def _apply_topn_and_sort(
    data: list[dict[str, Any]],
    intent: ChartIntent,
    group_by: str | None,
) -> list[dict[str, Any]]:
    if not data:
        return data

    value_key = AGG_VALUE_ALIAS

    if intent.top_n:
        if intent.series_field and group_by:
            totals: dict[str, float] = {}
            for item in data:
                group_key = str(item.get(group_by or ""))
                totals[group_key] = totals.get(group_key, 0.0) + float(
                    item.get(value_key, 0.0) or 0.0
                )
            ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
            top_groups = {group for group, _ in ranked[: intent.top_n]}
            data = [item for item in data if str(item.get(group_by or "")) in top_groups]
        else:
            data = sorted(
                data, key=lambda item: float(item.get(value_key, 0.0) or 0.0), reverse=True
            )
            data = data[: intent.top_n]

    if intent.sort and intent.sort != "none":
        reverse = intent.sort == "descending"
        data = sorted(
            data, key=lambda item: float(item.get(value_key, 0.0) or 0.0), reverse=reverse
        )

    return data


def _apply_scatter_sort_and_topn(
    data: list[dict[str, Any]],
    intent: ChartIntent,
) -> list[dict[str, Any]]:
    if not data:
        return data

    sort_field = intent.y_field or intent.x_field
    if intent.sort and intent.sort != "none" and sort_field:
        reverse = intent.sort == "descending"
        data = sorted(
            data,
            key=lambda item: _coerce_numeric(item.get(sort_field)) or 0.0,
            reverse=reverse,
        )

    if intent.top_n:
        data = data[: intent.top_n]

    return data


def _aggregate_scatter(rows: list[dict[str, Any]], intent: ChartIntent) -> list[dict[str, Any]]:
    if not intent.x_field or not intent.y_field:
        return []

    data = [row for row in rows if intent.x_field in row and intent.y_field in row]
    return _apply_scatter_sort_and_topn(data, intent)


def _apply_transforms(
    rows: list[dict[str, Any]],
    intent: ChartIntent,
) -> tuple[list[dict[str, Any]], str | None]:
    group_by = intent.group_by
    processed = rows

    if isinstance(intent.binning, BinningConfig):
        alias = intent.binning.alias or f"{intent.binning.field}_bin"
        processed = _apply_binning(
            processed, intent.binning.field, alias, intent.binning.bin_size, intent.binning.bins
        )
        group_by = group_by or alias

    if isinstance(intent.time_grain, TimeGrainConfig):
        alias = intent.time_grain.alias or f"{intent.time_grain.field}_{intent.time_grain.grain}"
        processed = _apply_time_grain(
            processed, intent.time_grain.field, intent.time_grain.grain, alias
        )
        group_by = group_by or alias

    return processed, group_by


def _apply_binning(
    rows: list[dict[str, Any]],
    field: str,
    alias: str,
    bin_size: int | None,
    bins: int | None,
) -> list[dict[str, Any]]:
    values = [
        _coerce_numeric(row.get(field))
        for row in rows
        if _coerce_numeric(row.get(field)) is not None
    ]
    if not values:
        return []

    min_val = min(values)
    max_val = max(values)

    if bin_size is None:
        if bins and bins > 0:
            span = max_val - min_val
            bin_size = int(max(1.0, (span / bins) if span > 0 else 1.0))
        else:
            bin_size = 10

    processed: list[dict[str, Any]] = []
    for row in rows:
        numeric = _coerce_numeric(row.get(field))
        label = "NULL"
        if numeric is not None and bin_size:
            start = int(numeric // bin_size) * bin_size
            end = start + bin_size - 1
            label = f"{start}-{end}"
        new_row = dict(row)
        new_row[alias] = label
        processed.append(new_row)

    return processed


def _apply_time_grain(
    rows: list[dict[str, Any]],
    field: str,
    grain: TimeGrain,
    alias: str,
) -> list[dict[str, Any]]:
    processed: list[dict[str, Any]] = []
    for row in rows:
        value = row.get(field)
        dt = _parse_datetime(value)
        label = "NULL"
        if dt:
            label = _format_time_grain(dt, grain)
        new_row = dict(row)
        new_row[alias] = label
        processed.append(new_row)
    return processed


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            try:
                from dateutil import parser  # type: ignore[import-not-found]

                return parser.parse(value)
            except Exception:
                return None
    return None


def _format_time_grain(dt: datetime, grain: TimeGrain) -> str:
    if grain == "day":
        return dt.date().isoformat()
    if grain == "week":
        year, week, _ = dt.isocalendar()
        return f"{year}-W{week:02d}"
    if grain == "month":
        return f"{dt.year}-{dt.month:02d}"
    if grain == "quarter":
        quarter = (dt.month - 1) // 3 + 1
        return f"{dt.year}-Q{quarter}"
    if grain == "year":
        return str(dt.year)
    return dt.date().isoformat()
