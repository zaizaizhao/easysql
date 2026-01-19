import { Table, Typography, Alert, Empty } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from 'react-i18next';
import type { ExecuteResponse } from '@/types';

const { Text } = Typography;

interface ResultTableProps {
  result: ExecuteResponse | null;
  loading?: boolean;
}

export function ResultTable({ result, loading }: ResultTableProps) {
  const { t } = useTranslation();

  if (loading) {
    return (
      <div style={{ padding: 24, textAlign: 'center', background: 'var(--bg-color-1)', borderRadius: 8 }}>
        <Text type="secondary">{t('common.loading')}</Text>
      </div>
    );
  }

  if (!result) return null;

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

  if (!result.data || result.data.length === 0) {
    return (
      <div style={{ 
        marginTop: 12, 
        padding: 24, 
        border: '1px solid var(--border-color)', 
        borderRadius: 8,
        background: 'var(--bg-color-1)'
      }}>
        <Empty 
          image={Empty.PRESENTED_IMAGE_SIMPLE} 
          description={
            result.affected_rows !== undefined 
              ? t('execute.affectedRows', { count: result.affected_rows }) 
              : t('execute.noData')
          } 
        />
      </div>
    );
  }

  const columns: ColumnsType<Record<string, any>> = (result.columns || []).map((col) => ({
    title: col,
    dataIndex: col,
    key: col,
    ellipsis: true,
    render: (value) => {
      if (value === null) return <Text type="secondary">NULL</Text>;
      if (typeof value === 'boolean') return value.toString();
      if (typeof value === 'object') return JSON.stringify(value);
      return String(value);
    },
  }));

  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {t('execute.resultStats', { 
            rows: result.row_count, 
            time: result.execution_time_ms?.toFixed(2) 
          })}
        </Text>
        {result.truncated && (
          <Text type="warning" style={{ fontSize: 12 }}>
            {t('execute.truncated')}
          </Text>
        )}
      </div>
      <Table
        dataSource={result.data}
        columns={columns}
        size="small"
        scroll={{ x: 'max-content', y: 400 }}
        pagination={{ 
          pageSize: 10, 
          showSizeChanger: false, 
          size: 'small',
          hideOnSinglePage: true
        }}
        rowKey={(_, index) => (index ?? Math.random()).toString()}
        style={{ border: '1px solid var(--border-color)', borderRadius: 8 }}
      />
    </div>
  );
}
