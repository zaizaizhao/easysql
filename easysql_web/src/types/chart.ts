/**
 * Chart Types and Configuration
 *
 * This module defines the data structures for chart visualization.
 * These types are designed to be compatible with LLM-generated configurations
 * and can be easily mapped to various charting libraries (ECharts, Ant Design Charts, etc.)
 */

/** Supported chart types */
export type ChartType =
  | 'bar'           // 柱形图 - 分类对比
  | 'line'          // 折线图 - 趋势变化
  | 'pie'           // 饼图 - 占比分布
  | 'scatter'       // 散点图 - 相关性分析
  | 'area'          // 面积图 - 累积趋势
  | 'horizontal_bar' // 横向柱形图 - 排名对比
  | 'donut'         // 环形图 - 占比分布（带中心）
  | 'grouped_bar'   // 分组柱形图 - 多维对比
  | 'stacked_bar'   // 堆叠柱形图 - 组成分析
  | 'stacked_area'  // 堆叠面积图 - 累积组成
  | 'metric_card';  // 数字卡片 - 单一指标

/** Data column type for inference */
export type ColumnDataType =
  | 'number'    // 数值型
  | 'string'    // 字符串/分类
  | 'date'      // 日期时间
  | 'boolean'   // 布尔值
  | 'unknown';  // 未知类型

/** Column metadata with inferred type */
export interface ColumnMeta {
  name: string;
  type: ColumnDataType;
  distinctCount?: number;  // 不同值的数量
  hasNull?: boolean;       // 是否包含空值
  sample?: unknown[];      // 采样值
}

/** Sort direction */
export type SortDirection = 'ascending' | 'descending' | 'none';

/** Legend position */
export type LegendPosition = 'top' | 'bottom' | 'left' | 'right' | 'none';

/** Aggregation type for chart intents */
export type AggType = 'count' | 'sum' | 'avg' | 'min' | 'max';

/** Layout type for multi-chart plans */
export type LayoutType = 'single' | 'grid' | 'tabs';

export type TimeGrain = 'day' | 'week' | 'month' | 'quarter' | 'year';

/**
 * Base chart configuration
 * This is the core structure that LLM will generate
 */
export interface ChartConfig {
  /** Chart type */
  chartType: ChartType;

  /** Chart title */
  title?: string;

  /** X-axis field name (for bar, line, scatter, area) */
  xField?: string;

  /** Y-axis field name (for bar, line, scatter, area) */
  yField?: string;

  /** Series/group field for multi-series charts */
  seriesField?: string;

  /** Angle field for pie/donut charts */
  angleField?: string;

  /** Color field for pie/donut charts */
  colorField?: string;

  /** Value field for metric card */
  valueField?: string;

  /** Label field for metric card */
  labelField?: string;

  /** Sort direction */
  sort?: SortDirection;

  /** Whether to show legend */
  showLegend?: boolean;

  /** Legend position */
  legendPosition?: LegendPosition;

  /** Whether to show data labels */
  showLabels?: boolean;

  /** Whether to enable smooth curve (for line/area) */
  smooth?: boolean;

  /** Whether to stack data (for bar/area) */
  stacked?: boolean;

  /** Color palette (optional override) */
  colors?: string[];

  /** X-axis label */
  xAxisLabel?: string;

  /** Y-axis label */
  yAxisLabel?: string;

  /** Number format pattern for values */
  valueFormat?: string;

  /** Percentage format for pie charts */
  showPercentage?: boolean;
}

/**
 * Chart recommendation request
 * Sent to backend LLM service
 */
export interface ChartRecommendRequest {
  /** Session ID for persisting chart plan */
  sessionId?: string;

  /** Turn ID for persisting chart plan */
  turnId?: string;

  /** Original user question (helps LLM understand intent) */
  question?: string;

  /** Generated SQL (provides context) */
  sql?: string;

  /** Column names */
  columns: string[];

  /** Column data types (if known) */
  columnTypes?: ColumnDataType[];

  /** Full result data for backend aggregation (optional) */
  data?: Record<string, unknown>[];

  /** Sample data (first 5-10 rows) */
  sampleData: Record<string, unknown>[];

  /** Total row count */
  rowCount: number;

  /** Previous visualization plan (for update/modify) */
  previousPlan?: VizPlan;

  /** Selected intent (skip planning and aggregate directly) */
  selectedIntent?: ChartIntent;

  /** Only return plan suggestions (no aggregation) */
  planOnly?: boolean;
}

/**
 * Chart recommendation response
 * Returned from backend LLM service
 */
export interface ChartRecommendResponse {
  /** Whether the data is suitable for visualization */
  suitable: boolean;

  /** Primary recommended chart configuration */
  config?: ChartConfig;

  /** Aggregated chart data (backend computed) */
  chartData?: ChartDataPoint[];

  /** Reasoning for the recommendation (can show as tooltip) */
  reasoning?: string;

  /** Alternative chart configurations */
  alternatives?: ChartConfig[];

  /** Error message if recommendation failed */
  error?: string;

  /** Primary intent used for aggregation */
  intent?: ChartIntent;

  /** Full visualization plan */
  plan?: VizPlan;
}

/** Minimal chart intent (LLM output) */
export interface ChartIntent {
  label?: string;
  chartType: ChartType;
  groupBy?: string;
  agg?: AggType;
  valueField?: string;
  seriesField?: string;
  topN?: number;
  sort?: SortDirection;
  title?: string;
  xField?: string;
  yField?: string;
  xAxisLabel?: string;
  yAxisLabel?: string;
  xUnit?: string;
  yUnit?: string;
  showPercentage?: boolean;
  binning?: BinningConfig;
  timeGrain?: TimeGrainConfig;
}

/** Visualization plan */
export interface VizPlan {
  suitable: boolean;
  charts: ChartIntent[];
  layout?: LayoutType;
  narrative?: string[];
  reasoning?: string;
}

export interface BinningConfig {
  field: string;
  binSize?: number;
  bins?: number;
  alias?: string;
}

export interface TimeGrainConfig {
  field: string;
  grain: TimeGrain;
  alias?: string;
}

/**
 * Chart data point - normalized format for rendering
 */
export type ChartDataPoint = Record<string, unknown>;

/**
 * Processed chart data ready for rendering
 */
export interface ChartData {
  /** Normalized data points */
  data: ChartDataPoint[];

  /** Column metadata */
  columns: ColumnMeta[];

  /** Chart configuration */
  config: ChartConfig;
}

/**
 * Chart render props - passed to chart components
 */
export interface ChartRenderProps {
  /** Chart data and config */
  chartData: ChartData;

  /** Chart height in pixels */
  height?: number;

  /** Whether the chart is in loading state */
  loading?: boolean;

  /** Theme mode */
  theme?: 'light' | 'dark';

  /** Callback when chart type changes */
  onChartTypeChange?: (type: ChartType) => void;

  /** Callback when user clicks on data point */
  onDataPointClick?: (data: ChartDataPoint, index: number) => void;
}

/**
 * Chart component state
 */
export interface ChartState {
  /** Current chart type */
  chartType: ChartType;

  /** Whether recommendation is loading */
  loading: boolean;

  /** Current chart configuration */
  config: ChartConfig | null;

  /** Error message */
  error: string | null;

  /** Alternative configurations */
  alternatives: ChartConfig[];
}

/**
 * Metric card data for single value display
 */
export interface MetricCardData {
  value: number | string;
  label?: string;
  prefix?: string;
  suffix?: string;
  precision?: number;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: number;
}
