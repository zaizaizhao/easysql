import { useState, useEffect, useRef } from 'react';
import { Button, Tooltip, message, Space, theme } from 'antd';
import {
  CopyOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  PlayCircleOutlined,
  LoadingOutlined,
  DownOutlined,
  RightOutlined,
  EditOutlined,
  TableOutlined,
  BarChartOutlined,
  StarOutlined,
  StarFilled,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import Editor from '@monaco-editor/react';
import { useAppStore } from '@/stores';
import { executeApi } from '@/api/execute';
import { fewShotApi } from '@/api/fewShot';
import type { ExecuteResponse } from '@/types';
import { ResultTable } from './ResultTable';
import { ResultChart } from '@/components/Chart';

interface SQLBlockProps {
  sql: string;
  validationPassed?: boolean;
  validationError?: string;
  autoExecute?: boolean;
  question?: string;
  messageId?: string;
  tablesUsed?: string[];
  isFewShot?: boolean;
  enableLlmCharts?: boolean;
}

export function SQLBlock({ 
  sql: initialSql, 
  validationPassed, 
  validationError, 
  autoExecute = false,
  question,
  messageId,
  tablesUsed,
  isFewShot: initialIsFewShot = false,
  enableLlmCharts = false,
}: SQLBlockProps) {
  const { t } = useTranslation();
  const { theme: appTheme, currentDatabase } = useAppStore();
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState<ExecuteResponse | null>(null);
  
  const [sqlCollapsed, setSqlCollapsed] = useState(false);
  const [resultCollapsed, setResultCollapsed] = useState(false);
  
  const [isEditing, setIsEditing] = useState(false);
  const [editedSql, setEditedSql] = useState(initialSql);
  const [isFewShot, setIsFewShot] = useState(initialIsFewShot);
  const [savingFewShot, setSavingFewShot] = useState(false);
  const { token } = theme.useToken();
  const hasAutoExecutedRef = useRef(false);
  const hasCheckedFewShotRef = useRef(false);

  const currentSql = isEditing ? editedSql : initialSql;

  useEffect(() => {
    if (messageId && !hasCheckedFewShotRef.current && !initialIsFewShot) {
      hasCheckedFewShotRef.current = true;
      fewShotApi.checkByMessageId(messageId)
        .then((response) => {
          if (response.is_few_shot) {
            setIsFewShot(true);
          }
        })
        .catch(() => {});
    }
  }, [messageId, initialIsFewShot]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(currentSql);
      message.success(t('sql.copySuccess'));
    } catch {
      message.error(t('sql.copyFailed'));
    }
  };

  const handleExecute = async () => {
    if (!currentDatabase) {
      message.error(t('chat.placeholderNoDb'));
      return;
    }

    setExecuting(true);
    setResult(null);
    setResultCollapsed(false); // Auto expand result on new execution

    try {
      const response = await executeApi.executeSql({
        sql: currentSql,
        db_name: currentDatabase,
      });
      setResult(response);
    } catch (error) {
      console.error('Execution failed:', error);
      setResult({
        status: 'failed',
        error: error instanceof Error ? error.message : String(error),
        row_count: 0,
        truncated: false
      });
    } finally {
      setExecuting(false);
    }
  };

  const handleToggleEdit = () => {
    if (!isEditing) {
      setEditedSql(initialSql);
    }
    setIsEditing(!isEditing);
  };

  const handleEditorChange = (value: string | undefined) => {
    if (value !== undefined) {
      setEditedSql(value);
    }
  };

  const handleSaveFewShot = async () => {
    if (!currentDatabase || !question) {
      message.warning(t('fewShot.missingInfo', 'Missing question or database'));
      return;
    }

    setSavingFewShot(true);
    try {
      await fewShotApi.create({
        db_name: currentDatabase,
        question: question,
        sql: currentSql,
        tables_used: tablesUsed,
        message_id: messageId,
      });
      setIsFewShot(true);
      message.success(t('fewShot.saveSuccess', 'Saved as example'));
    } catch (error) {
      console.error('Failed to save few-shot:', error);
      message.error(t('fewShot.saveFailed', 'Failed to save example'));
    } finally {
      setSavingFewShot(false);
    }
  };

  useEffect(() => {
    if (autoExecute && initialSql && currentDatabase && !hasAutoExecutedRef.current && !result) {
      hasAutoExecutedRef.current = true;
      handleExecute();
    }
  }, [autoExecute, initialSql, currentDatabase]);

  const lineCount = currentSql.split('\n').length;
  const editorHeight = Math.min(Math.max(lineCount * 19 + 24, 150), 600) + 'px';

  return (
    <div style={{ marginTop: 12 }}>
      {/* SQL Editor Section */}
      <div
        style={{
          border: `1px solid ${token.colorBorder}`,
          borderRadius: 8,
          overflow: 'hidden',
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.05)',
          background: token.colorBgContainer,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '8px 12px',
            background: token.colorFillQuaternary,
            borderBottom: sqlCollapsed ? 'none' : `1px solid ${token.colorBorder}`,
            cursor: 'pointer',
          }}
          onClick={() => setSqlCollapsed(!sqlCollapsed)}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {sqlCollapsed ? <RightOutlined style={{ fontSize: 12 }} /> : <DownOutlined style={{ fontSize: 12 }} />}
            <span style={{ fontWeight: 500, fontSize: 13 }}>{t('sql.title')}</span>
            {validationPassed !== undefined && (
              validationPassed ? (
                <Tooltip title={t('sql.validationPassed')}>
                  <CheckCircleOutlined style={{ color: '#52c41a' }} />
                </Tooltip>
              ) : (
                <Tooltip title={validationError || t('sql.validationFailed')}>
                  <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
                </Tooltip>
              )
            )}
            {isEditing && (
              <span style={{ fontSize: 11, color: token.colorWarning, fontWeight: 500 }}>
                ({t('sql.editing', 'Editing')})
              </span>
            )}
          </div>
          <Space onClick={(e) => e.stopPropagation()}>
            <Tooltip title={isEditing ? t('sql.cancelEdit', 'Cancel Edit') : t('sql.edit', 'Edit')}>
              <Button
                type={isEditing ? 'primary' : 'text'}
                size="small"
                icon={<EditOutlined />}
                onClick={handleToggleEdit}
              />
            </Tooltip>
            <Button
              type="primary"
              size="small"
              icon={executing ? <LoadingOutlined /> : <PlayCircleOutlined />}
              onClick={handleExecute}
              disabled={executing || !currentDatabase}
            >
              {executing ? t('execute.running') : t('execute.run')}
            </Button>
            <Button
              type="text"
              size="small"
              icon={<CopyOutlined />}
              onClick={handleCopy}
              aria-label={t('sql.copy')}
            >
              {t('sql.copy')}
            </Button>
            {question && (
              <Tooltip title={isFewShot ? t('fewShot.alreadySaved', 'Already saved') : t('fewShot.saveAsExample', 'Save as example')}>
                <Button
                  type="text"
                  size="small"
                  icon={isFewShot ? <StarFilled style={{ color: '#faad14' }} /> : savingFewShot ? <LoadingOutlined /> : <StarOutlined />}
                  onClick={handleSaveFewShot}
                  disabled={isFewShot || savingFewShot || !currentDatabase}
                />
              </Tooltip>
            )}
          </Space>
        </div>

        {!sqlCollapsed && (
          <Editor
            height={editorHeight}
            language="sql"
            value={currentSql}
            onChange={handleEditorChange}
            theme={appTheme === 'dark' ? 'vs-dark' : 'light'}
            options={{
              readOnly: !isEditing,
              minimap: { enabled: false },
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
              fontSize: 14,
              padding: { top: 12, bottom: 12 },
              folding: false,
              wordWrap: 'on',
              fontFamily: "'Fira Code', 'Menlo', 'Monaco', 'Courier New', monospace",
            }}
          />
        )}
      </div>

      {/* Result Table Section - Separate Block */}
      {(result || executing) && (
        <div
          style={{
            border: `1px solid ${token.colorBorder}`,
            borderRadius: 8,
            overflow: 'hidden',
            marginTop: 12,
            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.05)',
            background: token.colorBgContainer,
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              padding: '8px 12px',
              background: token.colorFillQuaternary,
              borderBottom: resultCollapsed ? 'none' : `1px solid ${token.colorBorder}`,
              cursor: 'pointer',
            }}
            onClick={() => setResultCollapsed(!resultCollapsed)}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {resultCollapsed ? <RightOutlined style={{ fontSize: 12 }} /> : <DownOutlined style={{ fontSize: 12 }} />}
              <Space>
                <TableOutlined />
                <span style={{ fontWeight: 500, fontSize: 13 }}>
                  {t('execute.resultTitle', 'Execution Result')}
                </span>
                {result && !executing && (
                  <span style={{ fontSize: 12, color: token.colorTextSecondary }}>
                    ({result.row_count} rows, {result.execution_time_ms ? Math.round(result.execution_time_ms) : 0}ms)
                  </span>
                )}
              </Space>
            </div>
          </div>

          {!resultCollapsed && (
            <div style={{ padding: '0 12px 12px 12px' }}>
              <ResultTable result={result} loading={executing} />
              <div style={{ marginTop: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <BarChartOutlined />
                  <span style={{ fontWeight: 500, fontSize: 13 }}>
                    {t('chart.views.chart', 'Chart')}
                  </span>
                </div>
                <ResultChart
                  result={result}
                  loading={executing}
                  question={question}
                  sql={currentSql}
                  useLlmRecommendation={enableLlmCharts}
                  height={350}
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
