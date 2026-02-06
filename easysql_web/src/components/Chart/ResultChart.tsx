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

import { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { Alert, Empty, Spin, Space, Button, Tooltip, Typography, theme, Card, Tag, message } from 'antd';
import {
  DownloadOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ExecuteResponse } from '@/types/execute';
import { saveTurnChartPlan } from '@/api';
import type {
  ChartConfig,
  ChartIntent,
  ChartType,
  ChartRecommendResponse,
  VizPlan,
} from '@/types/chart';
import { useChatStore } from '@/stores';
import { ChartRenderer } from './ChartRenderer';
import { ChartTypeSelector } from './ChartTypeSelector';
import { chartApi } from '@/api/chart';
import {
  analyzeColumns,
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
  /** Stored chart plan (for history replay) */
  storedPlan?: VizPlan;
  /** Stored chart reasoning (for history replay) */
  storedReasoning?: string;
  /** Turn ID for persisting chart plan */
  turnId?: string;
  /** External chart config (from LLM or parent component) */
  externalConfig?: ChartConfig;
  /** Callback when chart config changes */
  onConfigChange?: (config: ChartConfig | null) => void;
}

export function ResultChart({
  result,
  loading = false,
  question,
  sql,
  height = 350,
  useLlmRecommendation = false,
  storedPlan,
  storedReasoning,
  turnId,
  externalConfig,
  onConfigChange,
}: ResultChartProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const sessionId = useChatStore((state) => state.sessionId);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const persistedPlanKeyRef = useRef<string | null>(null);

  // Manual chart type override
  const [manualChartType, setManualChartType] = useState<ChartType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [llmPlan, setLlmPlan] = useState<VizPlan | null>(null);
  const [llmPlanReasoning, setLlmPlanReasoning] = useState<string | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [selectionLoading, setSelectionLoading] = useState(false);
  const [selectedIntent, setSelectedIntent] = useState<ChartIntent | null>(null);
  const [selectedResponse, setSelectedResponse] = useState<ChartRecommendResponse | null>(null);
  const [llmChartData, setLlmChartData] = useState<Record<string, unknown>[] | null>(null);

  // Track if we've already made a recommend call for this turn to prevent duplicates
  const recommendCalledRef = useRef<string | null>(null);

  useEffect(() => {
    if (!useLlmRecommendation) {
      setLlmPlan(null);
      setLlmPlanReasoning(null);
      setLlmChartData(null);
      setSelectedIntent(null);
      setSelectedResponse(null);
      setPlanLoading(false);
      setSelectionLoading(false);
      return;
    }

    if (storedPlan) {
      setLlmPlan(storedPlan);
      setLlmPlanReasoning(storedReasoning ?? null);
      setSelectedIntent(null);
      setSelectedResponse(null);
      setLlmChartData(null);
      setError(null);
      setPlanLoading(false);
      // Mark that we have a plan for this turn (prevent future calls)
      if (turnId) {
        recommendCalledRef.current = turnId;
      }
      return;
    }

    if (!result || result.status !== 'success' || !result.data || !result.columns) {
      setLlmPlan(null);
      setLlmPlanReasoning(null);
      setLlmChartData(null);
      setSelectedIntent(null);
      setSelectedResponse(null);
      setPlanLoading(false);
      setSelectionLoading(false);
      return;
    }

    if (externalConfig || manualChartType) {
      return;
    }

    // Prevent duplicate API calls for the same turn
    // This handles race conditions when storedPlan hasn't loaded yet
    if (turnId && recommendCalledRef.current === turnId) {
      return;
    }

    // Mark that we're making a recommend call for this turn
    if (turnId) {
      recommendCalledRef.current = turnId;
    }

    let cancelled = false;
    setPlanLoading(true);
    setError(null);
    setSelectedIntent(null);
    setSelectedResponse(null);
    setLlmChartData(null);
    const sampleData = result.data.slice(0, 10);
    const columnTypes = analyzeColumns(sampleData, result.columns).map((col) => col.type);

    chartApi
      .recommendChart({
        sessionId,
        turnId,
        question,
        sql,
        columns: result.columns,
        columnTypes,
        sampleData,
        rowCount: result.row_count,
        planOnly: true,
      })
      .then((response) => {
        if (cancelled) return;
        setLlmPlan(response.plan || null);
        setLlmPlanReasoning(response.reasoning || null);
        setError(response.error || null);
      })
      .catch((err) => {
        if (cancelled) return;
        setLlmPlan(null);
        setLlmPlanReasoning(null);
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (cancelled) return;
        setPlanLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [
    useLlmRecommendation,
    storedPlan,
    storedReasoning,
    result,
    question,
    sql,
    externalConfig,
    manualChartType,
    sessionId,
    turnId,
  ]);

  useEffect(() => {
    if (!useLlmRecommendation || storedPlan || !llmPlan || !sessionId || !turnId) {
      return;
    }
    const planKey = `${sessionId}:${turnId}:${JSON.stringify(llmPlan)}`;
    if (persistedPlanKeyRef.current === planKey) {
      return;
    }
    persistedPlanKeyRef.current = planKey;
    saveTurnChartPlan(sessionId, turnId, llmPlan, llmPlanReasoning).catch(() => {
      persistedPlanKeyRef.current = null;
    });
  }, [
    useLlmRecommendation,
    storedPlan,
    llmPlan,
    llmPlanReasoning,
    sessionId,
    turnId,
  ]);

  const llmModeActive = useLlmRecommendation && !!llmPlan?.charts?.length;
  const llmSelectedReady =
    llmModeActive && !!selectedResponse?.config && !!selectedResponse?.suitable && !!llmChartData;
  const activeIntent = selectedResponse?.intent || selectedIntent || null;

  const intentSummary = useMemo(() => {
    if (!activeIntent) return null;
    const agg = (activeIntent.agg || (activeIntent.valueField ? 'sum' : 'count')) as string;
    const aggLabel = t(`chart.agg.${agg}`, agg);
    const chartTypeLabel = t(`chart.types.${activeIntent.chartType}`, activeIntent.chartType);
    if (activeIntent.chartType === 'scatter' && activeIntent.xField && activeIntent.yField) {
      return t('chart.intentSummaryScatter', {
        chartType: chartTypeLabel,
        xField: activeIntent.xField,
        yField: activeIntent.yField,
      });
    }
    if (activeIntent.groupBy) {
      return t('chart.intentSummary', {
        chartType: chartTypeLabel,
        groupBy: activeIntent.groupBy,
        agg: aggLabel,
      });
    }
    return t('chart.intentSummaryNoGroup', {
      chartType: chartTypeLabel,
      agg: aggLabel,
    });
  }, [activeIntent, t]);

  const renderSuggestionMeta = useCallback(
    (intent: ChartIntent) => {
      const chartTypeLabel = t(`chart.types.${intent.chartType}`, intent.chartType);
      const agg = (intent.agg || (intent.valueField ? 'sum' : 'count')) as string;
      const aggLabel = t(`chart.agg.${agg}`, agg);
      if (intent.groupBy) {
        return `${chartTypeLabel} · ${aggLabel} · ${intent.groupBy}`;
      }
      if (intent.xField && intent.yField) {
        return `${chartTypeLabel} · ${intent.xField} vs ${intent.yField}`;
      }
      return `${chartTypeLabel} · ${aggLabel}`;
    },
    [t]
  );

  // Derive chart config from result or external config
  const { chartConfig, recommendation, isSuitable, chartData } = useMemo(() => {
    // If no result or invalid result
    if (!result || result.status !== 'success' || !result.data || !result.columns) {
      return { chartConfig: null, recommendation: null, isSuitable: false, chartData: null };
    }

    const data = result.data;
    const columns = result.columns;

    if (useLlmRecommendation && !llmSelectedReady) {
      return {
        chartConfig: null,
        recommendation: llmPlanReasoning ? { suitable: false, reasoning: llmPlanReasoning } : null,
        isSuitable: false,
        chartData: null,
      };
    }

    if (llmSelectedReady && !manualChartType && !externalConfig) {
      const mergedRecommendation = selectedResponse
        ? { ...selectedResponse, reasoning: selectedResponse.reasoning ?? llmPlanReasoning }
        : null;
      return {
        chartConfig: selectedResponse?.config ?? null,
        recommendation: mergedRecommendation,
        isSuitable: true,
        chartData: llmChartData,
      };
    }

    // Quick check: is data suitable at all?
    if (!chartApi.isDataSuitableForChart(data, columns)) {
      const rec: ChartRecommendResponse = { suitable: false, reasoning: t('chart.notSuitable') };
      return { chartConfig: null, recommendation: rec, isSuitable: false, chartData: null };
    }

    // If external config is provided, use it
    if (externalConfig) {
      return {
        chartConfig: externalConfig,
        recommendation: { suitable: true, config: externalConfig },
        isSuitable: true,
        chartData: data,
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
      return { chartConfig: null, recommendation: rec, isSuitable: false, chartData: null };
    }

    return {
      chartConfig: localConfig,
      recommendation: { suitable: true, config: localConfig },
      isSuitable: true,
      chartData: data,
    };
  }, [
    result,
    externalConfig,
    manualChartType,
    t,
    llmSelectedReady,
    selectedResponse,
    llmChartData,
    llmPlanReasoning,
    useLlmRecommendation,
  ]);

  // Compute available chart types
  const availableTypes = useMemo((): ChartType[] => {
    if (!result?.data || !result?.columns || !chartConfig) {
      return [];
    }

    if (llmModeActive && !manualChartType && !externalConfig) {
      return chartConfig ? [chartConfig.chartType] : [];
    }

    const alternatives = getAlternativeChartTypes(
      result.data,
      result.columns,
      chartConfig.chartType
    );
    return [chartConfig.chartType, ...alternatives];
  }, [result, chartConfig, llmModeActive, manualChartType, externalConfig]);

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

  const handleSelectSuggestion = useCallback(
    (intent: ChartIntent) => {
      if (!result?.data || !result.columns) return;
      setSelectedIntent(intent);
      setSelectedResponse(null);
      setLlmChartData(null);
      setSelectionLoading(true);
      setError(null);

      const sampleData = result.data.slice(0, 10);
      const columnTypes = analyzeColumns(sampleData, result.columns).map((col) => col.type);

      chartApi
        .recommendChart({
          sessionId,
          turnId,
          question,
          sql,
          columns: result.columns,
          columnTypes,
          data: result.data,
          sampleData,
          rowCount: result.row_count,
          selectedIntent: intent,
        })
        .then((response) => {
          setSelectedResponse(response);
          setLlmChartData(response.chartData || null);
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : String(err));
          setSelectedResponse(null);
          setLlmChartData(null);
        })
        .finally(() => {
          setSelectionLoading(false);
        });
    },
    [result, question, sql, sessionId, turnId]
  );

  const handleResetSuggestion = useCallback(() => {
    setSelectedIntent(null);
    setSelectedResponse(null);
    setLlmChartData(null);
    setError(null);
  }, []);

  // Handle export to PNG
  const handleExport = useCallback(() => {
    if (!chartContainerRef.current) return;

    const canvas = chartContainerRef.current.querySelector('canvas');
    if (!canvas) {
      message.warning(t('chart.exportNotSupported', 'Export is not supported for this chart'));
      return;
    }

    const link = document.createElement('a');
    link.download = `chart-${Date.now()}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
  }, []);

  // Handle retry
  const handleRetry = useCallback(() => {
    setManualChartType(null);
    setError(null);
    setSelectedIntent(null);
    setSelectedResponse(null);
    setLlmChartData(null);
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

  if (useLlmRecommendation && !planLoading && !llmModeActive && !llmSelectedReady) {
    return (
      <div
        style={{
          padding: 24,
          border: `1px solid ${token.colorBorder}`,
          borderRadius: 8,
          background: token.colorBgContainer,
        }}
      >
        <Alert
          message={t('chart.noSuggestions')}
          description={error || llmPlanReasoning || t('chart.inferFailed')}
          type="warning"
          showIcon
        />
      </div>
    );
  }

  // LLM suggestions (no selection yet)
  if (useLlmRecommendation && llmModeActive && !llmSelectedReady) {
    return (
      <div
        style={{
          padding: 24,
          border: `1px solid ${token.colorBorder}`,
          borderRadius: 8,
          background: token.colorBgContainer,
        }}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space size={8}>
            <Text strong>{t('chart.suggestionsTitle')}</Text>
            {llmPlanReasoning && (
              <Tooltip title={llmPlanReasoning}>
                <InfoCircleOutlined style={{ color: token.colorTextSecondary, cursor: 'pointer' }} />
              </Tooltip>
            )}
          </Space>
          {planLoading ? (
            <div style={{ textAlign: 'center', padding: 16 }}>
              <Spin />
              <div style={{ marginTop: 8 }}>
                <Text type="secondary">{t('chart.generating')}</Text>
              </div>
            </div>
          ) : error ? (
            <Alert
              message={t('chart.inferFailed')}
              description={error}
              type="error"
              showIcon
            />
          ) : llmPlan?.charts?.length ? (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                gap: 12,
              }}
            >
              {llmPlan.charts.map((intent, index) => {
                const label = intent.label || intent.title || `${t('chart.suggestion')} ${index + 1}`;
                const isLoading = selectionLoading && selectedIntent === intent;
                const meta = renderSuggestionMeta(intent);
                return (
                  <Card
                    key={`${label}-${index}`}
                    size="small"
                    hoverable={!selectionLoading}
                    onClick={() => handleSelectSuggestion(intent)}
                    style={{
                      borderColor: token.colorBorder,
                      cursor: selectionLoading ? 'not-allowed' : 'pointer',
                      opacity: selectionLoading && !isLoading ? 0.6 : 1,
                    }}
                  >
                    <Space direction="vertical" size={6} style={{ width: '100%' }}>
                      <Space size={6} wrap>
                        <Text strong style={{ fontSize: 13 }}>
                          {label}
                        </Text>
                        {isLoading && <Spin size="small" />}
                      </Space>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {meta}
                      </Text>
                      {intent.chartType && (
                        <Tag color="blue" style={{ margin: 0 }}>
                          {t(`chart.types.${intent.chartType}`, intent.chartType)}
                        </Tag>
                      )}
                    </Space>
                  </Card>
                );
              })}
            </div>
          ) : (
            <Text type="secondary">{t('chart.noSuggestions')}</Text>
          )}
          {!planLoading && (
            <Text type="secondary">{t('chart.selectSuggestion')}</Text>
          )}
        </Space>
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
          {llmModeActive && selectedIntent && (
            <Button size="small" onClick={handleResetSuggestion}>
              {t('chart.changeSuggestion')}
            </Button>
          )}
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
          data={chartData || result.data}
          config={chartConfig}
          height={height}
        />
      </div>
    </div>
  );
}
