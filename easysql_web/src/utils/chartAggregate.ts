import i18n from '@/i18n';
import type { ChartDataPoint, ChartIntent, TimeGrain } from '@/types/chart';

type AggType = 'count' | 'sum' | 'avg' | 'min' | 'max';

export const AGG_VALUE_ALIAS = '__value';

const BASE_VALUE_FIELD_HINTS = [
  'count',
  'cnt',
  'num',
  'total',
  'sum',
  'qty',
  'quantity',
  'amount',
  'people',
  'users',
  'orders',
];

function getLocaleValueFieldHints(): string[] {
  const localized = i18n.t('chart.valueFieldHints', { returnObjects: true }) as unknown;
  if (!Array.isArray(localized)) return [];
  return localized.filter((item): item is string => typeof item === 'string');
}

function getValueFieldHints(): string[] {
  return Array.from(new Set([...BASE_VALUE_FIELD_HINTS, ...getLocaleValueFieldHints()]));
}

export function aggregateChartData(
  rows: ChartDataPoint[],
  intent: ChartIntent | null
): ChartDataPoint[] {
  if (!rows || rows.length === 0 || !intent) {
    return [];
  }

  if (String(intent.chartType) === 'scatter') {
    return aggregateScatter(rows, intent);
  }

  const [processedRows, groupBy] = applyTransforms(rows, intent);
  if (!processedRows.length) {
    return [];
  }

  let agg: AggType = (intent.agg as AggType) || (intent.valueField ? 'sum' : 'count');
  const seriesField = intent.seriesField;
  let valueField = intent.valueField;

  if (agg === 'count' && !valueField) {
    const shouldInfer = groupBy
      ? isGroupedOnce(processedRows, groupBy)
      : processedRows.length === 1;
    if (shouldInfer) {
      valueField = inferValueField(processedRows, new Set([groupBy, seriesField]));
      if (valueField) {
        agg = 'sum';
      }
    }
  }

  if (String(intent.chartType) === 'metric_card') {
    return aggregateMetricCard(processedRows, agg, groupBy, valueField);
  }

  if (!groupBy) {
    return [];
  }

  const grouped = new Map<string, { total: number; count: number; min?: number; max?: number }>();

  for (const row of processedRows) {
    const groupValue = row[groupBy];
    const groupKey = groupValue == null ? 'NULL' : String(groupValue);
    const seriesKey = seriesField ? String(row[seriesField] ?? 'NULL') : null;
    const key = seriesKey ? `${groupKey}__${seriesKey}` : groupKey;

    const state = grouped.get(key) || { total: 0, count: 0 };
    if (agg === 'count') {
      state.total += 1;
      state.count += 1;
      grouped.set(key, state);
      continue;
    }

    const numeric = coerceNumeric(valueField ? row[valueField] : undefined);
    if (numeric == null) {
      grouped.set(key, state);
      continue;
    }
    state.total += numeric;
    state.count += 1;
    state.min = state.min == null ? numeric : Math.min(state.min, numeric);
    state.max = state.max == null ? numeric : Math.max(state.max, numeric);
    grouped.set(key, state);
  }

  const aggregated: ChartDataPoint[] = [];
  for (const [key, state] of grouped.entries()) {
    const [groupKey, seriesKey] = seriesField ? key.split('__') : [key, null];
    const value = computeAgg(state, agg);
    const item: ChartDataPoint = { [groupBy]: groupKey, [AGG_VALUE_ALIAS]: value };
    if (seriesField && seriesKey != null) {
      item[seriesField] = seriesKey;
    }
    aggregated.push(item);
  }

  return applyTopnAndSort(aggregated, intent, groupBy);
}

function aggregateMetricCard(
  rows: ChartDataPoint[],
  agg: AggType,
  groupBy?: string | null,
  valueField?: string | null
): ChartDataPoint[] {
  if (!groupBy) {
    const state = {
      total: 0,
      count: 0,
      min: undefined as number | undefined,
      max: undefined as number | undefined,
    };
    for (const row of rows) {
      if (agg === 'count') {
        state.total += 1;
        state.count += 1;
        continue;
      }
      const numeric = coerceNumeric(valueField ? row[valueField] : undefined);
      if (numeric == null) continue;
      state.total += numeric;
      state.count += 1;
      state.min = state.min == null ? numeric : Math.min(state.min, numeric);
      state.max = state.max == null ? numeric : Math.max(state.max, numeric);
    }
    return [{ [AGG_VALUE_ALIAS]: computeAgg(state, agg) }];
  }

  const grouped = new Map<string, { total: number; count: number; min?: number; max?: number }>();
  for (const row of rows) {
    const groupValue = row[groupBy];
    const groupKey = groupValue == null ? 'NULL' : String(groupValue);
    const state = grouped.get(groupKey) || { total: 0, count: 0 };
    if (agg === 'count') {
      state.total += 1;
      state.count += 1;
      grouped.set(groupKey, state);
      continue;
    }
    const numeric = coerceNumeric(valueField ? row[valueField] : undefined);
    if (numeric == null) {
      grouped.set(groupKey, state);
      continue;
    }
    state.total += numeric;
    state.count += 1;
    state.min = state.min == null ? numeric : Math.min(state.min, numeric);
    state.max = state.max == null ? numeric : Math.max(state.max, numeric);
    grouped.set(groupKey, state);
  }

  if (!grouped.size) return [];
  let bestKey = '';
  let bestValue = -Infinity;
  for (const [key, state] of grouped.entries()) {
    const value = Number(computeAgg(state, agg));
    if (value > bestValue) {
      bestValue = value;
      bestKey = key;
    }
  }
  return [{ [groupBy]: bestKey, [AGG_VALUE_ALIAS]: bestValue }];
}

function aggregateScatter(rows: ChartDataPoint[], intent: ChartIntent): ChartDataPoint[] {
  if (!intent.xField || !intent.yField) {
    return [];
  }
  const data = rows.filter((row) => intent.xField! in row && intent.yField! in row);
  return applyScatterSortAndTopn(data, intent);
}

function applyTransforms(
  rows: ChartDataPoint[],
  intent: ChartIntent
): [ChartDataPoint[], string | null] {
  let groupBy = intent.groupBy ?? null;
  let processed = rows;

  if (intent.binning) {
    const alias = intent.binning.alias || `${intent.binning.field}_bin`;
    processed = applyBinning(
      processed,
      intent.binning.field,
      alias,
      intent.binning.binSize,
      intent.binning.bins
    );
    if (groupBy == null || groupBy === intent.binning.field) {
      groupBy = alias;
    }
  }

  if (intent.timeGrain) {
    const alias = intent.timeGrain.alias || `${intent.timeGrain.field}_${intent.timeGrain.grain}`;
    processed = applyTimeGrain(processed, intent.timeGrain.field, intent.timeGrain.grain, alias);
    if (groupBy == null || groupBy === intent.timeGrain.field) {
      groupBy = alias;
    }
  }

  return [processed, groupBy];
}

function applyTopnAndSort(
  data: ChartDataPoint[],
  intent: ChartIntent,
  groupBy: string
): ChartDataPoint[] {
  if (!data.length) return data;
  const valueKey = AGG_VALUE_ALIAS;

  let result = data;

  if (intent.topN) {
    if (intent.seriesField && groupBy) {
      const totals = new Map<string, number>();
      for (const item of result) {
        const groupKey = String(item[groupBy] ?? '');
        totals.set(groupKey, (totals.get(groupKey) || 0) + Number(item[valueKey] || 0));
      }
      const ranked = Array.from(totals.entries()).sort((a, b) => b[1] - a[1]);
      const topGroups = new Set(ranked.slice(0, intent.topN).map(([key]) => key));
      result = result.filter((item) => topGroups.has(String(item[groupBy] ?? '')));
    } else {
      result = [...result].sort((a, b) => Number(b[valueKey] || 0) - Number(a[valueKey] || 0));
      result = result.slice(0, intent.topN);
    }
  }

  if (intent.sort && intent.sort !== 'none') {
    const reverse = intent.sort === 'descending';
    result = [...result].sort((a, b) => {
      const diff = Number(a[valueKey] || 0) - Number(b[valueKey] || 0);
      return reverse ? -diff : diff;
    });
  }

  return result;
}

function applyScatterSortAndTopn(data: ChartDataPoint[], intent: ChartIntent): ChartDataPoint[] {
  let result = data;
  const sortField = intent.yField || intent.xField;
  if (intent.sort && intent.sort !== 'none' && sortField) {
    const reverse = intent.sort === 'descending';
    result = [...result].sort((a, b) => {
      const diff =
        Number(coerceNumeric(a[sortField]) || 0) -
        Number(coerceNumeric(b[sortField]) || 0);
      return reverse ? -diff : diff;
    });
  }

  if (intent.topN) {
    result = result.slice(0, intent.topN);
  }

  return result;
}

function applyBinning(
  rows: ChartDataPoint[],
  field: string,
  alias: string,
  binSize?: number,
  bins?: number
): ChartDataPoint[] {
  const valueParser = buildBinningValueParser(field);
  const values = rows
    .map((row) => valueParser(row[field]))
    .filter((value): value is number => value != null);

  if (!values.length) return [];

  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);

  let resolvedBinSize = binSize;
  if (!resolvedBinSize) {
    if (bins && bins > 0) {
      const span = maxVal - minVal;
      resolvedBinSize = Math.max(1, Math.floor(span > 0 ? span / bins : 1));
    } else {
      resolvedBinSize = 10;
    }
  }

  const processed: ChartDataPoint[] = [];
  for (const row of rows) {
    const numeric = valueParser(row[field]);
    let label = 'NULL';
    if (numeric != null && resolvedBinSize) {
      const start = Math.floor(numeric / resolvedBinSize) * resolvedBinSize;
      const end = start + resolvedBinSize - 1;
      label = `${start}-${end}`;
    }
    processed.push({ ...row, [alias]: label });
  }

  return processed;
}

function applyTimeGrain(
  rows: ChartDataPoint[],
  field: string,
  grain: TimeGrain,
  alias: string
): ChartDataPoint[] {
  return rows.map((row) => {
    const dt = parseDate(row[field]);
    const label = dt ? formatTimeGrain(dt, grain) : 'NULL';
    return { ...row, [alias]: label };
  });
}

function buildBinningValueParser(field: string) {
  const lowerField = field.toLowerCase();
  const isBirthField = ['birth', 'dob', 'birthday'].some((token) => lowerField.includes(token));

  return (value: unknown): number | null => {
    const numeric = coerceNumeric(value);
    if (numeric != null) {
      return numeric;
    }
    const dt = parseDate(value);
    if (!dt) return null;
    if (isBirthField) {
      return ageYears(dt);
    }
    return dt.getUTCFullYear();
  };
}

function ageYears(date: Date): number {
  const today = new Date();
  let years = today.getUTCFullYear() - date.getUTCFullYear();
  const monthDiff = today.getUTCMonth() - date.getUTCMonth();
  if (monthDiff < 0 || (monthDiff === 0 && today.getUTCDate() < date.getUTCDate())) {
    years -= 1;
  }
  return Math.max(0, years);
}

function parseDate(value: unknown): Date | null {
  if (value == null) return null;
  if (value instanceof Date) return isNaN(value.getTime()) ? null : value;
  const parsed = new Date(String(value));
  return isNaN(parsed.getTime()) ? null : parsed;
}

function formatTimeGrain(date: Date, grain: TimeGrain): string {
  const year = date.getUTCFullYear();
  const month = date.getUTCMonth() + 1;
  switch (grain) {
    case 'day':
      return date.toISOString().slice(0, 10);
    case 'week':
      return formatIsoWeek(date);
    case 'month':
      return `${year}-${String(month).padStart(2, '0')}`;
    case 'quarter': {
      const quarter = Math.floor((month - 1) / 3) + 1;
      return `${year}-Q${quarter}`;
    }
    case 'year':
      return String(year);
    default:
      return date.toISOString().slice(0, 10);
  }
}

function formatIsoWeek(date: Date): string {
  const temp = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  const dayNum = temp.getUTCDay() || 7;
  temp.setUTCDate(temp.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(temp.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil(((temp.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return `${temp.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`;
}

function coerceNumeric(value: unknown): number | null {
  if (value == null) return null;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function computeAgg(
  state: { total: number; count: number; min?: number; max?: number },
  agg: AggType
): number {
  switch (agg) {
    case 'count':
      return state.count;
    case 'sum':
      return state.total;
    case 'avg':
      return state.count ? state.total / state.count : 0;
    case 'min':
      return state.min ?? 0;
    case 'max':
      return state.max ?? 0;
    default:
      return state.total;
  }
}

function isGroupedOnce(rows: ChartDataPoint[], groupBy: string, sampleSize = 50): boolean {
  const sample = rows.slice(0, sampleSize);
  const counts = new Map<string, number>();
  for (const row of sample) {
    const key = row[groupBy];
    const keyStr = key == null ? 'NULL' : String(key);
    const next = (counts.get(keyStr) || 0) + 1;
    if (next > 1) return false;
    counts.set(keyStr, next);
  }
  return true;
}

function inferValueField(
  rows: ChartDataPoint[],
  excludeFields: Set<string | null>,
  sampleSize = 50
): string | null {
  const hints = getValueFieldHints();

  const exclude = new Set(Array.from(excludeFields).filter(Boolean) as string[]);
  const sample = rows.slice(0, sampleSize);
  const numericHits = new Map<string, number>();

  for (const row of sample) {
    for (const key of Object.keys(row)) {
      if (exclude.has(key)) continue;
      if (coerceNumeric(row[key]) != null) {
        numericHits.set(key, (numericHits.get(key) || 0) + 1);
      }
    }
  }

  if (!numericHits.size) return null;
  const threshold = Math.max(1, Math.floor(sample.length * 0.6));
  const numericFields = Array.from(numericHits.entries())
    .filter(([, hits]) => hits >= threshold)
    .map(([key]) => key);

  for (const key of numericFields) {
    const lowerKey = key.toLowerCase();
    if (hints.some((hint) => lowerKey.includes(hint))) {
      return key;
    }
  }

  if (numericFields.length === 1) {
    return numericFields[0];
  }

  return null;
}
