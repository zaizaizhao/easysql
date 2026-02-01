/**
 * Chart Type Inference Utility
 *
 * Rule-based engine for automatically inferring the best chart type
 * based on data characteristics. This serves as a fast fallback when
 * LLM recommendation is not available or for simple cases.
 */

import type {
  ChartConfig,
  ChartType,
  ColumnDataType,
  ColumnMeta,
  ChartDataPoint,
} from '@/types/chart';

/**
 * Infer the data type of a column based on sample values
 */
export function inferColumnType(values: unknown[]): ColumnDataType {
  const nonNullValues = values.filter((v) => v !== null && v !== undefined);

  if (nonNullValues.length === 0) {
    return 'unknown';
  }

  // Check if all values are numbers
  const allNumbers = nonNullValues.every((v) => {
    if (typeof v === 'number') return true;
    if (typeof v === 'string') {
      const parsed = parseFloat(v);
      return !isNaN(parsed) && isFinite(parsed);
    }
    return false;
  });

  if (allNumbers) {
    return 'number';
  }

  // Check if all values are booleans
  const allBooleans = nonNullValues.every(
    (v) => typeof v === 'boolean' || v === 'true' || v === 'false' || v === 0 || v === 1
  );

  if (allBooleans) {
    return 'boolean';
  }

  // Check if values look like dates
  const datePatterns = [
    /^\d{4}-\d{2}-\d{2}/, // ISO date
    /^\d{2}\/\d{2}\/\d{4}/, // US date
    /^\d{4}\/\d{2}\/\d{2}/, // Alternative ISO
  ];

  const allDates = nonNullValues.every((v) => {
    if (typeof v !== 'string') return false;
    return datePatterns.some((p) => p.test(v)) || !isNaN(Date.parse(v));
  });

  if (allDates) {
    return 'date';
  }

  return 'string';
}

/**
 * Analyze columns and extract metadata
 */
export function analyzeColumns(
  data: ChartDataPoint[],
  columns: string[]
): ColumnMeta[] {
  return columns.map((name) => {
    const values = data.map((row) => row[name]);
    const nonNullValues = values.filter((v) => v !== null && v !== undefined);
    const distinctValues = new Set(nonNullValues.map((v) => String(v)));

    return {
      name,
      type: inferColumnType(values),
      distinctCount: distinctValues.size,
      hasNull: values.some((v) => v === null || v === undefined),
      sample: nonNullValues.slice(0, 5),
    };
  });
}

/**
 * Find columns by type
 */
function findColumnsByType(
  columnMetas: ColumnMeta[],
  type: ColumnDataType
): ColumnMeta[] {
  return columnMetas.filter((col) => col.type === type);
}

/**
 * Check if a column is suitable for category axis (limited distinct values)
 */
function isCategoryColumn(col: ColumnMeta, maxCategories = 30): boolean {
  return (
    (col.type === 'string' || col.type === 'boolean') &&
    col.distinctCount !== undefined &&
    col.distinctCount <= maxCategories
  );
}

/**
 * Check if data is suitable for pie chart
 */
function isSuitableForPie(
  categoryCol: ColumnMeta,
  _numericCol: ColumnMeta,
  rowCount: number
): boolean {
  return (
    categoryCol.distinctCount !== undefined &&
    categoryCol.distinctCount <= 8 &&
    categoryCol.distinctCount >= 2 &&
    rowCount <= 20
  );
}

/**
 * Infer the best chart configuration based on data characteristics
 */
export function inferChartConfig(
  data: ChartDataPoint[],
  columns: string[],
  options?: {
    preferredType?: ChartType;
    title?: string;
  }
): ChartConfig | null {
  if (!data || data.length === 0 || !columns || columns.length === 0) {
    return null;
  }

  const columnMetas = analyzeColumns(data, columns);
  const numericCols = findColumnsByType(columnMetas, 'number');
  const stringCols = findColumnsByType(columnMetas, 'string');
  const dateCols = findColumnsByType(columnMetas, 'date');
  const categoryCols = columnMetas.filter((col) => isCategoryColumn(col));

  const rowCount = data.length;

  // If preferred type is specified and valid, try to use it
  if (options?.preferredType) {
    const config = buildConfigForType(
      options.preferredType,
      columnMetas,
      numericCols,
      stringCols,
      dateCols,
      categoryCols
    );
    if (config) {
      config.title = options.title;
      return config;
    }
  }

  // Single row with numeric value -> Metric Card
  if (rowCount === 1 && numericCols.length >= 1) {
    return {
      chartType: 'metric_card',
      valueField: numericCols[0].name,
      labelField: stringCols.length > 0 ? stringCols[0].name : undefined,
      title: options?.title,
    };
  }

  // Date column + numeric column -> Line Chart
  if (dateCols.length >= 1 && numericCols.length >= 1) {
    return {
      chartType: 'line',
      xField: dateCols[0].name,
      yField: numericCols[0].name,
      seriesField: numericCols.length > 1 ? undefined : stringCols[0]?.name,
      smooth: true,
      showLegend: stringCols.length > 0,
      title: options?.title,
    };
  }

  // Category column + numeric column
  if (categoryCols.length >= 1 && numericCols.length >= 1) {
    const categoryCol = categoryCols[0];
    const numericCol = numericCols[0];

    // Few categories -> consider Pie
    if (isSuitableForPie(categoryCol, numericCol, rowCount)) {
      return {
        chartType: 'pie',
        angleField: numericCol.name,
        colorField: categoryCol.name,
        showLabels: true,
        showPercentage: true,
        showLegend: true,
        legendPosition: 'right',
        title: options?.title,
      };
    }

    // Multiple numeric columns with category -> Grouped Bar
    if (numericCols.length > 1 && categoryCols.length === 1) {
      return {
        chartType: 'grouped_bar',
        xField: categoryCol.name,
        yField: numericCols[0].name,
        seriesField: numericCols[1]?.name,
        showLegend: true,
        title: options?.title,
      };
    }

    // Standard case -> Bar Chart
    // Use horizontal bar for long category names or many categories
    const avgCategoryLength =
      (categoryCol.sample || []).reduce<number>(
        (sum, v) => sum + String(v).length,
        0
      ) / (categoryCol.sample?.length || 1);

    const isHorizontal =
      avgCategoryLength > 10 ||
      (categoryCol.distinctCount !== undefined && categoryCol.distinctCount > 10);

    return {
      chartType: isHorizontal ? 'horizontal_bar' : 'bar',
      xField: isHorizontal ? numericCol.name : categoryCol.name,
      yField: isHorizontal ? categoryCol.name : numericCol.name,
      sort: 'descending',
      showLabels: rowCount <= 15,
      title: options?.title,
    };
  }

  // Two numeric columns -> Scatter
  if (numericCols.length >= 2) {
    return {
      chartType: 'scatter',
      xField: numericCols[0].name,
      yField: numericCols[1].name,
      colorField: stringCols[0]?.name,
      showLegend: stringCols.length > 0,
      title: options?.title,
    };
  }

  // Single numeric column with string column -> Bar
  if (numericCols.length === 1 && stringCols.length >= 1) {
    return {
      chartType: 'bar',
      xField: stringCols[0].name,
      yField: numericCols[0].name,
      sort: 'descending',
      title: options?.title,
    };
  }

  // Cannot determine suitable chart
  return null;
}

/**
 * Build configuration for a specific chart type
 */
function buildConfigForType(
  type: ChartType,
  columnMetas: ColumnMeta[],
  numericCols: ColumnMeta[],
  stringCols: ColumnMeta[],
  dateCols: ColumnMeta[],
  categoryCols: ColumnMeta[]
): ChartConfig | null {
  switch (type) {
    case 'bar':
    case 'horizontal_bar':
      if (numericCols.length >= 1 && (stringCols.length >= 1 || categoryCols.length >= 1)) {
        const categoryCol = categoryCols[0] || stringCols[0];
        const isHorizontal = type === 'horizontal_bar';
        return {
          chartType: type,
          xField: isHorizontal ? numericCols[0].name : categoryCol.name,
          yField: isHorizontal ? categoryCol.name : numericCols[0].name,
          sort: 'descending',
        };
      }
      break;

    case 'line':
    case 'area':
      if (numericCols.length >= 1 && (dateCols.length >= 1 || stringCols.length >= 1)) {
        return {
          chartType: type,
          xField: dateCols[0]?.name || stringCols[0]?.name,
          yField: numericCols[0].name,
          smooth: true,
        };
      }
      break;

    case 'pie':
    case 'donut':
      if (numericCols.length >= 1 && categoryCols.length >= 1) {
        return {
          chartType: type,
          angleField: numericCols[0].name,
          colorField: categoryCols[0].name,
          showLabels: true,
          showPercentage: true,
        };
      }
      break;

    case 'scatter':
      if (numericCols.length >= 2) {
        return {
          chartType: type,
          xField: numericCols[0].name,
          yField: numericCols[1].name,
          colorField: stringCols[0]?.name,
        };
      }
      break;

    case 'metric_card':
      if (numericCols.length >= 1) {
        return {
          chartType: type,
          valueField: numericCols[0].name,
          labelField: stringCols[0]?.name,
        };
      }
      break;

    case 'grouped_bar':
    case 'stacked_bar':
      if (numericCols.length >= 1 && categoryCols.length >= 1) {
        return {
          chartType: type,
          xField: categoryCols[0].name,
          yField: numericCols[0].name,
          seriesField: stringCols[1]?.name || categoryCols[1]?.name,
          stacked: type === 'stacked_bar',
        };
      }
      break;

    case 'stacked_area':
      if (numericCols.length >= 1 && (dateCols.length >= 1 || columnMetas.length >= 2)) {
        return {
          chartType: type,
          xField: dateCols[0]?.name || stringCols[0]?.name,
          yField: numericCols[0].name,
          seriesField: stringCols[0]?.name,
          stacked: true,
        };
      }
      break;
  }

  return null;
}

/**
 * Get alternative chart types that could work with the data
 */
export function getAlternativeChartTypes(
  data: ChartDataPoint[],
  columns: string[],
  currentType: ChartType
): ChartType[] {
  const columnMetas = analyzeColumns(data, columns);
  const numericCols = findColumnsByType(columnMetas, 'number');
  const stringCols = findColumnsByType(columnMetas, 'string');
  const dateCols = findColumnsByType(columnMetas, 'date');

  const alternatives: ChartType[] = [];

  // Bar family
  if (numericCols.length >= 1 && stringCols.length >= 1) {
    if (currentType !== 'bar') alternatives.push('bar');
    if (currentType !== 'horizontal_bar') alternatives.push('horizontal_bar');
  }

  // Line/Area for time series
  if (numericCols.length >= 1 && (dateCols.length >= 1 || stringCols.length >= 1)) {
    if (currentType !== 'line') alternatives.push('line');
    if (currentType !== 'area') alternatives.push('area');
  }

  // Pie for limited categories
  if (numericCols.length >= 1 && stringCols.length >= 1 && data.length <= 10) {
    if (currentType !== 'pie') alternatives.push('pie');
    if (currentType !== 'donut') alternatives.push('donut');
  }

  // Scatter for numeric pairs
  if (numericCols.length >= 2) {
    if (currentType !== 'scatter') alternatives.push('scatter');
  }

  return alternatives.slice(0, 4); // Return max 4 alternatives
}

/**
 * Validate if a chart config is valid for the given data
 */
export function validateChartConfig(
  config: ChartConfig,
  data: ChartDataPoint[],
  columns: string[]
): { valid: boolean; errors: string[] } {
  const errors: string[] = [];
  const columnSet = new Set(columns);

  // Check required fields based on chart type
  switch (config.chartType) {
    case 'bar':
    case 'horizontal_bar':
    case 'line':
    case 'area':
    case 'grouped_bar':
    case 'stacked_bar':
    case 'stacked_area':
      if (!config.xField || !columnSet.has(config.xField)) {
        errors.push(`Invalid xField: ${config.xField}`);
      }
      if (!config.yField || !columnSet.has(config.yField)) {
        errors.push(`Invalid yField: ${config.yField}`);
      }
      break;

    case 'pie':
    case 'donut':
      if (!config.angleField || !columnSet.has(config.angleField)) {
        errors.push(`Invalid angleField: ${config.angleField}`);
      }
      if (!config.colorField || !columnSet.has(config.colorField)) {
        errors.push(`Invalid colorField: ${config.colorField}`);
      }
      break;

    case 'scatter':
      if (!config.xField || !columnSet.has(config.xField)) {
        errors.push(`Invalid xField: ${config.xField}`);
      }
      if (!config.yField || !columnSet.has(config.yField)) {
        errors.push(`Invalid yField: ${config.yField}`);
      }
      break;

    case 'metric_card':
      if (!config.valueField || !columnSet.has(config.valueField)) {
        errors.push(`Invalid valueField: ${config.valueField}`);
      }
      break;
  }

  // Check data requirements
  if (data.length === 0) {
    errors.push('No data available');
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

/**
 * Format number for display
 */
export function formatChartValue(
  value: unknown,
  format?: string
): string {
  if (value === null || value === undefined) {
    return '-';
  }

  const numValue = typeof value === 'number' ? value : parseFloat(String(value));

  if (isNaN(numValue)) {
    return String(value);
  }

  // Apply format pattern
  if (format === 'percent') {
    return `${(numValue * 100).toFixed(1)}%`;
  }

  if (format === 'currency') {
    return new Intl.NumberFormat('zh-CN', {
      style: 'currency',
      currency: 'CNY',
    }).format(numValue);
  }

  // Default number formatting
  if (Math.abs(numValue) >= 1000000) {
    return `${(numValue / 1000000).toFixed(1)}M`;
  }

  if (Math.abs(numValue) >= 1000) {
    return `${(numValue / 1000).toFixed(1)}K`;
  }

  if (Number.isInteger(numValue)) {
    return numValue.toLocaleString();
  }

  return numValue.toFixed(2);
}
