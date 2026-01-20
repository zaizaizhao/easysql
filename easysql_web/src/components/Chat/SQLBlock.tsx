import { useState } from 'react';
import { Button, Tooltip, message, Space, theme } from 'antd';
import { CopyOutlined, CheckCircleOutlined, CloseCircleOutlined, PlayCircleOutlined, LoadingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import Editor from '@monaco-editor/react';
import { useAppStore } from '@/stores';
import { executeApi } from '@/api/execute';
import type { ExecuteResponse } from '@/types';
import { ResultTable } from './ResultTable';

interface SQLBlockProps {
  sql: string;
  validationPassed?: boolean;
  validationError?: string;
}

export function SQLBlock({ sql, validationPassed, validationError }: SQLBlockProps) {
  const { t } = useTranslation();
  const { theme: appTheme, currentDatabase } = useAppStore();
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState<ExecuteResponse | null>(null);
  const { token } = theme.useToken();

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
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

    try {
      const response = await executeApi.executeSql({
        sql,
        db_name: currentDatabase,
      });
      setResult(response);
    } catch (error) {
      console.error('Execution failed:', error);
      // Error is handled by API interceptor usually, but we set local state too
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

  const lineCount = sql.split('\n').length;
  const editorHeight = Math.min(Math.max(lineCount * 19 + 24, 150), 600) + 'px';

  return (
    <div
      style={{
        border: `1px solid ${token.colorBorder}`,
        borderRadius: 8,
        overflow: 'hidden',
        marginTop: 12,
        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.05)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 12px',
          background: token.colorFillQuaternary,
          borderBottom: `1px solid ${token.colorBorder}`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
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
        </div>
        <Space>
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
          >
            {t('sql.copy')}
          </Button>
        </Space>
      </div>

      <Editor
        height={editorHeight}
        language="sql"
        value={sql}
        theme={appTheme === 'dark' ? 'vs-dark' : 'light'}
        options={{
          readOnly: true,
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
      
      {(result || executing) && (
        <div style={{ padding: '0 12px 12px 12px', borderTop: `1px solid ${token.colorBorder}` }}>
          <ResultTable result={result} loading={executing} />
        </div>
      )}
    </div>
  );
}
