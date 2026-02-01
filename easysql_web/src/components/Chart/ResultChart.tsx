/**
 * ResultChart
 *
 * Main chart visualization component for SQL execution results.
 * This is the counterpart of ResultTable - renders data as charts
 * instead of tabular format.
 *
 * Features:
 * - Auto-infers chart type from data characteristics
 * - Supports LLM-recommended chart configurations
 * - Allows manual chart type switching
 * - Handles loading, error, and empty states
 * - Theme-aware (dark/light mode)
 * - Export to PNG
 */

import { useState, useMemo, useCallback, useRef } from 'react';
import { Alert, Empty, Spin, Space, Button, Tooltip, Typography, theme } from 'antd';
import {
  DownloadOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ExecuteResponse } from '@/types/execute';
import type { ChartConfig, ChartType, ChartRecommendResponse } from '@/types/chart';
import { ChartRenderer } from './ChartRenderer';
import { ChartTypeSelector } from './ChartTypeSelector';
import { chartApi } from '@/api/chart';
import {
  inferChartConfig,
  getAlternativeChartTypes,
} from '@/utils/chartInfer';

const { Text } = Typography;

interface ResultChartProps {
  /** SQL execution result */
  result: ExecuteResponse | null;
  /** Whether data is loading */
  loading?: boolean;
  /** Original user question (for LLM context) */
  question?: string;
  /** SQL that produced the result (for LLM context) */
  sql?: string;
  /** Chart height in pixels */
  height?: number;
  /** Whether to use LLM recommendation (requires backend API) */
  useLlmRecommendation?: boolean;
  /** External chart config (from LLM or parent component) */
  externalConfig?: ChartConfig;
  /** Callback when chart config changes */
  onConfigChange?: (config: ChartConfig | null) => void;
}

export function ResultChart({
  result,
  loading = false,
  // Reserved for LLM recommendation feature
  // question,
  // sql,
  height = 350,
  // useLlmRecommendation = false,
  externalConfig,
  onConfigChange,
}: ResultChartProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const chartContainerRef = useRef<HTMLDivElement>(null);

  // Manual chart type override
  const [manualChartType, setManualChartType] = useState<ChartType | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Derive chart config from result or external config
  const { chartConfig, recommendation, isSuitable } = useMemo(() => {
    // If no result or invalid result
    if (!result || result.status !== 'success' || !result.data || !result.columns) {
      return { chartConfig: null, recommendation: null, isSuitable: false };
    }

    const data = result.data;
    const columns = result.columns;

    // Quick check: is data suitable at all?
    if (!chartApi.isDataSuitableForChart(data, columns)) {
      const rec: ChartRecommendResponse = { suitable: false, reasoning: t('chart.notSuitable') };
      return { chartConfig: null, recommendation: rec, isSuitable: false };
    }

    // If external config is provided, use it
    if (externalConfig) {
      return {
        chartConfig: externalConfig,
        recommendation: { suitable: true, config: externalConfig },
        isSuitable: true,
      };
    }

    // Use local inference (LLM recommendation would be triggered via button)
    const localConfig = inferChartConfig(data, columns, {
      preferredType: manualChartType ?? undefined,
    });

    if (!localConfig) {
      const rec: ChartRecommendResponse = {
        suitable: false,
        reasoning: t('chart.inferFailed'),
      };
      return { chartConfig: null, recommendation: rec, isSuitable: false };
    }

    return {
      chartConfig: localConfig,
      recommendation: { suitable: true, config: localConfig },
      isSuitable: true,
    };
  }, [result, externalConfig, manualChartType, t]);

  // Compute available chart types
  const availableTypes = useMemo((): ChartType[] => {
    if (!result?.data || !result?.columns || !chartConfig) {
      return [];
    }

    const alternatives = getAlternativeChartTypes(
      result.data,
      result.columns,
      chartConfig.chartType
    );
    return [chartConfig.chartType, ...alternatives];
  }, [result, chartConfig]);

  // Handle chart type change
  const handleChartTypeChange = useCallback(
    (newType: ChartType) => {
      setManualChartType(newType);
      if (result?.data && result?.columns) {
        const newConfig = inferChartConfig(result.data, result.columns, {
          preferredType: newType,
          title: chartConfig?.title,
        });
        onConfigChange?.(newConfig);
      }
    },
    [result, chartConfig, onConfigChange]
  );

  // Handle export to PNG
  const handleExport = useCallback(() => {
    if (!chartContainerRef.current) return;

    const canvas = chartContainerRef.current.querySelector('canvas');
    if (!canvas) return;

    const link = document.createElement('a');
    link.download = `chart-${Date.now()}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
  }, []);

  // Handle retry
  const handleRetry = useCallback(() => {
    setManualChartType(null);
    setError(null);
  }, []);

  // Loading state
  if (loading) {
    return (
      <div
        style={{
          padding: 48,
          textAlign: 'center',
          background: token.colorBgContainer,
          borderRadius: 8,
        }}
      >
        <Spin />
        <div style={{ marginTop: 12 }}>
          <Text type="secondary">{t('common.loading')}</Text>
        </div>
      </div>
    );
  }

  // No result
  if (!result) return null;

  // Error state
  if (result.status !== 'success') {
    return (
      <Alert
        message={t('execute.error')}
        description={result.error}
        type="error"
        showIcon
        style={{ marginTop: 12 }}
      />
    );
  }

  // No data
  if (!result.data || result.data.length === 0) {
    return (
      <div
        style={{
          padding: 24,
          border: `1px solid ${token.colorBorder}`,
          borderRadius: 8,
          background: token.colorBgContainer,
        }}
      >
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t('execute.noData')}
        />
      </div>
    );
  }

  // Not suitable for chart
  if (!isSuitable || !chartConfig) {
    return (
      <div
        style={{
          padding: 24,
          textAlign: 'center',
          border: `1px solid ${token.colorBorder}`,
          borderRadius: 8,
          background: token.colorBgContainer,
        }}
      >
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <span>
              {recommendation?.reasoning || t('chart.notSuitable')}
              {recommendation?.reasoning && (
                <Tooltip title={recommendation.reasoning}>
                  <InfoCircleOutlined style={{ marginLeft: 8, cursor: 'pointer' }} />
                </Tooltip>
              )}
            </span>
          }
        />
      </div>
    );
  }

  // Error with retry
  if (error) {
    return (
      <div
        style={{
          padding: 24,
          textAlign: 'center',
          border: `1px solid ${token.colorBorder}`,
          borderRadius: 8,
          background: token.colorBgContainer,
        }}
      >
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={error}
        />
        <Button
          size="small"
          icon={<ReloadOutlined />}
          onClick={handleRetry}
          style={{ marginTop: 12 }}
        >
          {t('chart.retry')}
        </Button>
      </div>
    );
  }

  return (
    <div>
      {/* Chart toolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 8,
        }}
      >
        <Space size={8}>
          {chartConfig.title && (
            <Text strong style={{ fontSize: 13 }}>
              {chartConfig.title}
            </Text>
          )}
          {recommendation?.reasoning && (
            <Tooltip title={recommendation.reasoning}>
              <InfoCircleOutlined
                style={{ color: token.colorTextSecondary, cursor: 'pointer', fontSize: 12 }}
              />
            </Tooltip>
          )}
        </Space>
        <Space size={8}>
          {availableTypes.length > 1 && (
            <ChartTypeSelector
              value={chartConfig.chartType}
              onChange={handleChartTypeChange}
              availableTypes={availableTypes}
            />
          )}
          <Tooltip title={t('chart.export')}>
            <Button
              type="text"
              size="small"
              icon={<DownloadOutlined />}
              onClick={handleExport}
            />
          </Tooltip>
        </Space>
      </div>

      {/* Chart content */}
      <div
        ref={chartContainerRef}
        style={{
          background: token.colorBgContainer,
          borderRadius: 8,
          padding: 16,
          border: `1px solid ${token.colorBorder}`,
        }}
      >
        <ChartRenderer
          data={result.data}
          config={chartConfig}
          height={height}
        />
      </div>
    </div>
  );
}
