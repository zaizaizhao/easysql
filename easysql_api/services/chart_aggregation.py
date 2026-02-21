"""
Chart data aggregation helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, cast

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
    if isinstance(value, int | float):
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


def _normalize_agg(raw_agg: AggType | str | None, has_value_field: bool) -> AggType:
    if raw_agg in {"count", "sum", "avg", "min", "max"}:
        return cast(AggType, raw_agg)
    return "count" if not has_value_field else "sum"


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

    agg = _normalize_agg(intent.agg, has_value_field=bool(intent.value_field))
    series_field = intent.series_field
    value_field = intent.value_field

    if agg == "count" and not value_field:
        should_infer = False
        if group_by:
            should_infer = _is_grouped_once(processed_rows, group_by)
        elif len(processed_rows) == 1:
            should_infer = True

        if should_infer:
            value_field = _infer_value_field(
                processed_rows,
                exclude_fields={group_by, series_field},
            )
            if value_field:
                agg = "sum"

    if str(intent.chart_type) == "metric_card":
        return _aggregate_metric_card(processed_rows, intent, agg, group_by, value_field)

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

        numeric = _coerce_numeric(row.get(value_field or ""))
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
    value_field: str | None,
) -> list[dict[str, Any]]:
    if not group_by:
        state = _AggState()
        for row in rows:
            if agg == "count":
                state.update(1.0)
                continue
            numeric = _coerce_numeric(row.get(value_field or ""))
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
        numeric = _coerce_numeric(row.get(value_field or ""))
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
        if group_by is None or group_by == intent.binning.field:
            group_by = alias

    if isinstance(intent.time_grain, TimeGrainConfig):
        alias = intent.time_grain.alias or f"{intent.time_grain.field}_{intent.time_grain.grain}"
        processed = _apply_time_grain(
            processed, intent.time_grain.field, intent.time_grain.grain, alias
        )
        if group_by is None or group_by == intent.time_grain.field:
            group_by = alias

    return processed, group_by


def _is_grouped_once(rows: list[dict[str, Any]], group_by: str, sample_size: int = 50) -> bool:
    if not rows:
        return False
    sample = rows[:sample_size]
    counts: dict[str, int] = {}
    for row in sample:
        key = row.get(group_by)
        key_str = "NULL" if key is None else str(key)
        counts[key_str] = counts.get(key_str, 0) + 1
        if counts[key_str] > 1:
            return False
    return True


def _infer_value_field(
    rows: list[dict[str, Any]],
    exclude_fields: set[str | None],
    sample_size: int = 50,
) -> str | None:
    if not rows:
        return None

    hints = (
        "count",
        "cnt",
        "num",
        "total",
        "sum",
        "qty",
        "quantity",
        "amount",
        "people",
        "users",
        "orders",
        "人数",
        "人次",
        "数量",
        "次数",
        "用户数",
        "订单数",
    )

    exclude = {field for field in exclude_fields if field}
    sample = rows[:sample_size]
    numeric_hits: dict[str, int] = {}

    for row in sample:
        for key, value in row.items():
            if key in exclude:
                continue
            if _coerce_numeric(value) is not None:
                numeric_hits[key] = numeric_hits.get(key, 0) + 1

    if not numeric_hits:
        return None

    threshold = max(1, int(len(sample) * 0.6))
    numeric_fields = [key for key, hits in numeric_hits.items() if hits >= threshold]
    if not numeric_fields:
        return None

    for key in numeric_fields:
        lower_key = key.lower()
        if any(hint in lower_key for hint in hints):
            return key

    if len(numeric_fields) == 1:
        return numeric_fields[0]

    return None


def _build_binning_value_parser(field: str):
    lower_field = field.lower()
    is_birth_field = any(token in lower_field for token in ("birth", "dob", "birthday"))

    def _parse(value: object) -> float | None:
        numeric = _coerce_numeric(value)
        if numeric is not None:
            return numeric
        dt = _parse_datetime(value)
        if not dt:
            return None
        if is_birth_field:
            return _age_years(dt)
        return float(dt.year)

    return _parse


def _age_years(dt: datetime) -> float:
    today = datetime.utcnow().date()
    years = today.year - dt.year
    if (today.month, today.day) < (dt.month, dt.day):
        years -= 1
    return float(max(years, 0))


def _apply_binning(
    rows: list[dict[str, Any]],
    field: str,
    alias: str,
    bin_size: int | None,
    bins: int | None,
) -> list[dict[str, Any]]:
    value_parser = _build_binning_value_parser(field)
    values = [
        value_parser(row.get(field)) for row in rows if value_parser(row.get(field)) is not None
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
        numeric = value_parser(row.get(field))
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
                from dateutil import parser as dateutil_parser  # type: ignore[import-untyped]

                parsed = dateutil_parser.parse(value)
                if isinstance(parsed, datetime):
                    return parsed
                return None
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
