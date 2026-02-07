import type { ChartConfig, ChartIntent, ChartType } from '@/types/chart';
import { AGG_VALUE_ALIAS } from '@/utils/chartAggregate';

const SUPPORTED_CHART_TYPES = new Set<ChartType>([
  'bar',
  'line',
  'pie',
  'scatter',
  'area',
  'horizontal_bar',
  'donut',
  'grouped_bar',
  'stacked_bar',
  'stacked_area',
  'metric_card',
]);

function formatAxisLabel(label?: string, unit?: string): string | undefined {
  if (!label) return undefined;
  if (!unit) return label;
  if (label.includes(unit)) return label;
  return `${label} (${unit})`;
}

function resolveGroupBy(intent: ChartIntent): string | null {
  let groupBy = intent.groupBy ?? null;

  if (intent.binning) {
    const alias = intent.binning.alias || `${intent.binning.field}_bin`;
    if (!groupBy || groupBy === intent.binning.field) {
      groupBy = alias;
    }
  }

  if (intent.timeGrain) {
    const alias = intent.timeGrain.alias || `${intent.timeGrain.field}_${intent.timeGrain.grain}`;
    if (!groupBy || groupBy === intent.timeGrain.field) {
      groupBy = alias;
    }
  }

  return groupBy;
}

export function buildChartConfigFromIntent(intent: ChartIntent | null): ChartConfig | null {
  if (!intent) return null;

  const chartType = intent.chartType as ChartType;
  if (!SUPPORTED_CHART_TYPES.has(chartType)) {
    return null;
  }

  let groupBy = resolveGroupBy(intent);

  if (
    chartType === 'bar' ||
    chartType === 'line' ||
    chartType === 'area' ||
    chartType === 'grouped_bar' ||
    chartType === 'stacked_bar' ||
    chartType === 'stacked_area'
  ) {
    if (!groupBy) return null;
    return {
      chartType,
      title: intent.title,
      xField: groupBy,
      yField: AGG_VALUE_ALIAS,
      seriesField: intent.seriesField,
      sort: intent.sort,
      stacked: chartType === 'stacked_bar' || chartType === 'stacked_area',
      xAxisLabel: formatAxisLabel(intent.xAxisLabel, intent.xUnit),
      yAxisLabel: formatAxisLabel(intent.yAxisLabel, intent.yUnit),
    };
  }

  if (chartType === 'horizontal_bar') {
    if (!groupBy) return null;
    return {
      chartType,
      title: intent.title,
      xField: AGG_VALUE_ALIAS,
      yField: groupBy,
      seriesField: intent.seriesField,
      sort: intent.sort,
      xAxisLabel: formatAxisLabel(intent.yAxisLabel, intent.yUnit),
      yAxisLabel: formatAxisLabel(intent.xAxisLabel, intent.xUnit),
    };
  }

  if (chartType === 'pie' || chartType === 'donut') {
    if (!groupBy) return null;
    return {
      chartType,
      title: intent.title,
      angleField: AGG_VALUE_ALIAS,
      colorField: groupBy,
      showLegend: true,
      showLabels: true,
      showPercentage: intent.showPercentage ?? true,
    };
  }

  if (chartType === 'metric_card') {
    return {
      chartType,
      title: intent.title,
      valueField: AGG_VALUE_ALIAS,
      labelField: intent.groupBy,
    };
  }

  if (chartType === 'scatter') {
    if (!intent.xField || !intent.yField) return null;
    return {
      chartType,
      title: intent.title,
      xField: intent.xField,
      yField: intent.yField,
      seriesField: intent.seriesField,
      xAxisLabel: formatAxisLabel(intent.xAxisLabel, intent.xUnit),
      yAxisLabel: formatAxisLabel(intent.yAxisLabel, intent.yUnit),
    };
  }

  return null;
}
