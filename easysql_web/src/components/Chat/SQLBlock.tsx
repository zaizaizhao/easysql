import { Button, Tooltip, message } from 'antd';
import { CopyOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import Editor from '@monaco-editor/react';
import { useAppStore } from '@/stores';

interface SQLBlockProps {
  sql: string;
  validationPassed?: boolean;
  validationError?: string;
}

export function SQLBlock({ sql, validationPassed, validationError }: SQLBlockProps) {
  const { t } = useTranslation();
  const { theme } = useAppStore();

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      message.success(t('sql.copySuccess'));
    } catch {
      message.error(t('sql.copyFailed'));
    }
  };

  const lineCount = sql.split('\n').length;
  const editorHeight = Math.min(Math.max(lineCount * 19 + 24, 150), 600) + 'px';

  return (
    <div
      style={{
        border: '1px solid var(--border-color)',
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
          background: 'var(--code-header-bg)',
          borderBottom: '1px solid var(--border-color)',
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
        <Button
          type="text"
          size="small"
          icon={<CopyOutlined />}
          onClick={handleCopy}
        >
          {t('sql.copy')}
        </Button>
      </div>

      <Editor
        height={editorHeight}
        language="sql"
        value={sql}
        theme={theme === 'dark' ? 'vs-dark' : 'light'}
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
    </div>
  );
}
