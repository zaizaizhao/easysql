/**
 * Chart API Service
 *
 * Handles communication with backend chart recommendation service.
 * Falls back to local inference when backend is unavailable.
 */

import { apiClient } from './client';
import type {
  ChartRecommendRequest,
  ChartRecommendResponse,
  ChartConfig,
} from '@/types/chart';
import { inferChartConfig, analyzeColumns } from '@/utils/chartInfer';

// LLM calls may take longer than default 30s timeout
const LLM_TIMEOUT = 120000;

/**
 * Request chart recommendation from backend LLM service
 */
async function recommendChart(
  request: ChartRecommendRequest
): Promise<ChartRecommendResponse> {
  const response = await apiClient.post<ChartRecommendResponse>(
    '/chart/recommend',
    request,
    { timeout: LLM_TIMEOUT }
  );
  return response.data;
}

/**
 * Get chart recommendation with fallback to local inference
 *
 * @param request Chart recommendation request
 * @param useLocalFallback Whether to use local inference if backend fails
 */
async function getChartRecommendation(
  request: ChartRecommendRequest,
  useLocalFallback = true
): Promise<ChartRecommendResponse> {
  try {
    // Try backend LLM recommendation first
    return await recommendChart(request);
  } catch (error) {
    console.warn('Chart recommendation API failed, using local inference:', error);

    if (!useLocalFallback) {
      return {
        suitable: false,
        error: error instanceof Error ? error.message : 'Failed to get recommendation',
      };
    }

    // Fallback to local rule-based inference
    return getLocalRecommendation(request);
  }
}

/**
 * Get chart recommendation using local rule-based inference
 */
function getLocalRecommendation(
  request: ChartRecommendRequest
): ChartRecommendResponse {
  const { columns, sampleData, rowCount } = request;

  if (!sampleData || sampleData.length === 0 || !columns || columns.length === 0) {
    return {
      suitable: false,
      reasoning: 'No data available for visualization',
    };
  }

  // Analyze column types
  const columnMetas = analyzeColumns(sampleData, columns);

  // Check if data is suitable for visualization
  const numericColumns = columnMetas.filter((col) => col.type === 'number');

  if (numericColumns.length === 0) {
    return {
      suitable: false,
      reasoning: 'No numeric columns found for visualization',
    };
  }

  // Infer chart configuration
  const config = inferChartConfig(sampleData, columns);

  if (!config) {
    return {
      suitable: false,
      reasoning: 'Could not determine suitable chart type for this data',
    };
  }

  // Generate reasoning
  const reasoning = generateReasoning(config, columnMetas, rowCount);

  // Generate alternatives
  const alternatives = generateAlternatives(config, sampleData, columns);

  return {
    suitable: true,
    config,
    reasoning,
    alternatives,
  };
}

/**
 * Generate human-readable reasoning for chart recommendation
 */
function generateReasoning(
  config: ChartConfig,
  columnMetas: ReturnType<typeof analyzeColumns>,
  rowCount: number
): string {
  const numericCols = columnMetas.filter((c) => c.type === 'number').length;
  const categoryCols = columnMetas.filter((c) => c.type === 'string').length;
  const dateCols = columnMetas.filter((c) => c.type === 'date').length;

  const parts: string[] = [];

  parts.push(`数据包含 ${rowCount} 行`);
  parts.push(`${numericCols} 个数值列`);

  if (categoryCols > 0) {
    parts.push(`${categoryCols} 个分类列`);
  }

  if (dateCols > 0) {
    parts.push(`${dateCols} 个日期列`);
  }

  const chartTypeNames: Record<string, string> = {
    bar: '柱形图适合展示分类对比',
    horizontal_bar: '横向柱形图适合展示排名',
    line: '折线图适合展示趋势变化',
    area: '面积图适合展示累积趋势',
    pie: '饼图适合展示占比分布',
    donut: '环形图适合展示占比分布',
    scatter: '散点图适合分析相关性',
    metric_card: '数字卡片适合展示关键指标',
    grouped_bar: '分组柱形图适合多维对比',
    stacked_bar: '堆叠柱形图适合组成分析',
    stacked_area: '堆叠面积图适合累积组成',
  };

  parts.push(chartTypeNames[config.chartType] || '');

  return parts.filter(Boolean).join('，');
}

/**
 * Generate alternative chart configurations
 */
function generateAlternatives(
  primaryConfig: ChartConfig,
  data: Record<string, unknown>[],
  columns: string[]
): ChartConfig[] {
  const alternatives: ChartConfig[] = [];
  const alternativeTypes: Array<{ type: ChartConfig['chartType']; priority: number }> = [];

  // Determine alternative types based on primary type
  switch (primaryConfig.chartType) {
    case 'bar':
      alternativeTypes.push({ type: 'horizontal_bar', priority: 1 });
      alternativeTypes.push({ type: 'pie', priority: 2 });
      alternativeTypes.push({ type: 'line', priority: 3 });
      break;

    case 'line':
      alternativeTypes.push({ type: 'area', priority: 1 });
      alternativeTypes.push({ type: 'bar', priority: 2 });
      break;

    case 'pie':
      alternativeTypes.push({ type: 'donut', priority: 1 });
      alternativeTypes.push({ type: 'bar', priority: 2 });
      alternativeTypes.push({ type: 'horizontal_bar', priority: 3 });
      break;

    case 'scatter':
      alternativeTypes.push({ type: 'line', priority: 1 });
      break;

    default:
      alternativeTypes.push({ type: 'bar', priority: 1 });
  }

  // Generate configs for alternatives
  for (const { type } of alternativeTypes.sort((a, b) => a.priority - b.priority)) {
    const altConfig = inferChartConfig(data, columns, { preferredType: type });
    if (altConfig && altConfig.chartType !== primaryConfig.chartType) {
      alternatives.push(altConfig);
    }
  }

  return alternatives.slice(0, 3);
}

/**
 * Check if data is suitable for chart visualization (quick check)
 */
function isDataSuitableForChart(
  data: Record<string, unknown>[],
  columns: string[]
): boolean {
  if (!data || data.length === 0 || !columns || columns.length === 0) {
    return false;
  }

  // At least 1 row
  if (data.length < 1) {
    return false;
  }

  // At least 1 numeric column
  const columnMetas = analyzeColumns(data, columns);
  const hasNumeric = columnMetas.some((col) => col.type === 'number');

  return hasNumeric;
}

export const chartApi = {
  recommendChart,
  getChartRecommendation,
  getLocalRecommendation,
  isDataSuitableForChart,
};
