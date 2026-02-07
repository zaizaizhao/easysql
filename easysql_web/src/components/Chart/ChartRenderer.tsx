/**
 * ChartRenderer
 *
 * Core chart rendering component that maps ChartConfig to @ant-design/charts components.
 * Handles all supported chart types with proper configuration mapping.
 */

import { useMemo } from 'react';
import { Column, Bar, Line, Area, Pie, Scatter } from '@ant-design/charts';
import { theme, Empty, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import type { ChartConfig, ChartDataPoint } from '@/types/chart';
import { MetricCard } from './MetricCard';
import { formatChartValue, validateChartConfig } from '@/utils/chartInfer';

const { Text } = Typography;

interface ChartRendererProps {
  data: ChartDataPoint[];
  config: ChartConfig;
  height?: number;
}

/**
 * Coerce string values to numbers where the config expects numeric fields
 */
function coerceNumericFields(
  data: ChartDataPoint[],
  numericFields: (string | undefined)[]
): ChartDataPoint[] {
  const fields = numericFields.filter(Boolean) as string[];
  if (fields.length === 0) return data;

  return data.map((row) => {
    const newRow = { ...row };
    for (const field of fields) {
      const val = newRow[field];
      if (typeof val === 'string') {
        const parsed = parseFloat(val);
        if (!isNaN(parsed)) {
          newRow[field] = parsed;
        }
      }
    }
    return newRow;
  });
}

/**
 * Build common axis configuration
 */
function buildAxisConfig(label?: string) {
  if (!label) return {};
  return { title: label };
}

export function ChartRenderer({ data, config, height = 350 }: ChartRendererProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();

  // Prepare data with type coercion
  const chartData = useMemo(() => {
    const numericFields: (string | undefined)[] = [];

    switch (config.chartType) {
      case 'bar':
      case 'horizontal_bar':
      case 'grouped_bar':
      case 'stacked_bar':
        numericFields.push(config.yField);
        break;
      case 'line':
      case 'area':
      case 'stacked_area':
        numericFields.push(config.yField);
        break;
      case 'scatter':
        numericFields.push(config.xField, config.yField);
        break;
      case 'pie':
      case 'donut':
        numericFields.push(config.angleField);
        break;
      case 'metric_card':
        numericFields.push(config.valueField);
        break;
    }

    let processed = coerceNumericFields(data, numericFields);

    // Sort if specified
    if (config.sort && config.sort !== 'none') {
      const sortField = config.yField || config.angleField;
      if (sortField) {
        processed = [...processed].sort((a, b) => {
          const va = Number(a[sortField]) || 0;
          const vb = Number(b[sortField]) || 0;
          return config.sort === 'descending' ? vb - va : va - vb;
        });
      }
    }

    return processed;
  }, [data, config]);

  if (!data || data.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('chart.noData')} />;
  }

  const validation = useMemo(() => {
    const columns = chartData.length > 0 ? Object.keys(chartData[0] ?? {}) : [];
    return validateChartConfig(config, chartData, columns);
  }, [chartData, config]);

  if (!validation.valid) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('chart.inferFailed')} />;
  }

  const themeColors = [
    token.colorPrimary,
    token.colorSuccess,
    token.colorWarning,
    token.colorError,
    token.colorInfo,
    '#722ed1',
    '#13c2c2',
    '#fa8c16',
    '#eb2f96',
    '#52c41a',
  ];

  const palette = config.colors || themeColors;

  // Metric card
  if (config.chartType === 'metric_card') {
    const valueField = config.valueField || Object.keys(data[0])[0];
    const labelField = config.labelField;
    return (
      <MetricCard
        data={{
          value: data[0][valueField] as number | string,
          label: labelField ? String(data[0][labelField] ?? '') : config.title,
        }}
        height={height}
      />
    );
  }

  // Bar chart (vertical columns in @ant-design/charts)
  if (config.chartType === 'bar') {
    return (
      <Column
        data={chartData}
        xField={config.xField!}
        yField={config.yField!}
        colorField={config.seriesField}
        height={height}
        style={{ fill: palette[0], maxWidth: 40 }}
        axis={{
          x: buildAxisConfig(config.xAxisLabel),
          y: buildAxisConfig(config.yAxisLabel),
        }}
        label={
          config.showLabels
            ? { text: (d: ChartDataPoint) => formatChartValue(d[config.yField!]) }
            : undefined
        }
        tooltip={{ title: (d: ChartDataPoint) => String(d[config.xField!]) }}
      />
    );
  }

  // Horizontal bar
  if (config.chartType === 'horizontal_bar') {
    return (
      <Bar
        data={chartData}
        xField={config.xField!}
        yField={config.yField!}
        height={height}
        style={{ fill: palette[0], maxWidth: 28 }}
        axis={{
          x: buildAxisConfig(config.xAxisLabel),
          y: buildAxisConfig(config.yAxisLabel),
        }}
        label={
          config.showLabels
            ? { text: (d: ChartDataPoint) => formatChartValue(d[config.xField!]) }
            : undefined
        }
      />
    );
  }

  // Line chart
  if (config.chartType === 'line') {
    return (
      <Line
        data={chartData}
        xField={config.xField!}
        yField={config.yField!}
        colorField={config.seriesField}
        height={height}
        shapeField={config.smooth ? 'smooth' : 'line'}
        axis={{
          x: buildAxisConfig(config.xAxisLabel),
          y: buildAxisConfig(config.yAxisLabel),
        }}
        point={{ shapeField: 'point', sizeField: 3 }}
        legend={config.showLegend ? { position: config.legendPosition || 'top' } : false}
      />
    );
  }

  // Area chart
  if (config.chartType === 'area' || config.chartType === 'stacked_area') {
    return (
      <Area
        data={chartData}
        xField={config.xField!}
        yField={config.yField!}
        colorField={config.seriesField}
        height={height}
        shapeField={config.smooth ? 'smooth' : undefined}
        stack={config.stacked || config.chartType === 'stacked_area'}
        axis={{
          x: buildAxisConfig(config.xAxisLabel),
          y: buildAxisConfig(config.yAxisLabel),
        }}
        legend={config.showLegend ? { position: config.legendPosition || 'top' } : false}
      />
    );
  }

  // Pie / Donut chart
  if (config.chartType === 'pie' || config.chartType === 'donut') {
    return (
      <Pie
        data={chartData}
        angleField={config.angleField!}
        colorField={config.colorField!}
        height={height}
        innerRadius={config.chartType === 'donut' ? 0.6 : 0}
        label={{
          text: config.showPercentage
            ? (d: ChartDataPoint) => {
                const total = chartData.reduce(
                  (sum, item) => sum + (Number(item[config.angleField!]) || 0),
                  0
                );
                const val = Number(d[config.angleField!]) || 0;
                const pct = total > 0 ? ((val / total) * 100).toFixed(1) : '0';
                return `${d[config.colorField!]}: ${pct}%`;
              }
            : (d: ChartDataPoint) => String(d[config.colorField!]),
        }}
        legend={
          config.showLegend !== false
            ? { position: config.legendPosition || 'right' }
            : false
        }
        tooltip={{
          title: (d: ChartDataPoint) => String(d[config.colorField!]),
        }}
      />
    );
  }

  // Scatter chart
  if (config.chartType === 'scatter') {
    return (
      <Scatter
        data={chartData}
        xField={config.xField!}
        yField={config.yField!}
        colorField={config.colorField}
        height={height}
        axis={{
          x: buildAxisConfig(config.xAxisLabel),
          y: buildAxisConfig(config.yAxisLabel),
        }}
        legend={config.showLegend ? { position: config.legendPosition || 'top' } : false}
      />
    );
  }

  // Grouped / Stacked bar
  if (config.chartType === 'grouped_bar' || config.chartType === 'stacked_bar') {
    return (
      <Column
        data={chartData}
        xField={config.xField!}
        yField={config.yField!}
        colorField={config.seriesField}
        height={height}
        group={config.chartType === 'grouped_bar'}
        stack={config.chartType === 'stacked_bar'}
        axis={{
          x: buildAxisConfig(config.xAxisLabel),
          y: buildAxisConfig(config.yAxisLabel),
        }}
        legend={{ position: config.legendPosition || 'top' }}
      />
    );
  }

  return (
    <div style={{ padding: 24, textAlign: 'center' }}>
      <Text type="secondary">{t('chart.unsupportedType')}</Text>
    </div>
  );
}
