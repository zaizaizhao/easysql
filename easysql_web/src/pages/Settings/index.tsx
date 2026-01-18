import { Card, Descriptions, Tag, Typography, Divider, Button, Space, Spin, Progress, message } from 'antd';
import { SyncOutlined, CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';

import { useConfig, usePipelineStatus, useRunPipeline } from '@/hooks';

const { Title, Text } = Typography;

export default function SettingsPage() {
  const { t } = useTranslation();
  const { data: config, isLoading: configLoading } = useConfig();
  const { data: pipelineStatus, isLoading: statusLoading } = usePipelineStatus();
  const runPipeline = useRunPipeline();

  const handleSync = async () => {
    try {
      await runPipeline.mutateAsync({});
      message.success(t('settings.pipelineStarted'));
    } catch {
      message.error(t('settings.pipelineStartFailed'));
    }
  };

  const renderPipelineStatus = () => {
    if (statusLoading) return <Spin size="small" />;
    if (!pipelineStatus) return <Text type="secondary">{t('common.unknown')}</Text>;

    const statusConfig: Record<string, { icon: React.ReactNode; color: string; text: string }> = {
      idle: { icon: <ClockCircleOutlined />, color: 'default', text: t('settings.statusIdle') },
      running: { icon: <SyncOutlined spin />, color: 'processing', text: t('settings.statusRunning') },
      completed: { icon: <CheckCircleOutlined />, color: 'success', text: t('settings.statusCompleted') },
      failed: { icon: <CloseCircleOutlined />, color: 'error', text: t('settings.statusFailed') },
    };

    const cfg = statusConfig[pipelineStatus.status] || statusConfig.idle;

    return (
      <Space>
        <Tag icon={cfg.icon} color={cfg.color}>{cfg.text}</Tag>
        {pipelineStatus.started_at && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {dayjs(pipelineStatus.started_at).format('YYYY-MM-DD HH:mm:ss')}
          </Text>
        )}
      </Space>
    );
  };

  if (configLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 900 }}>
      <Title level={4}>{t('settings.title')}</Title>

      <Card title={t('settings.schemaSync')} style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <Text strong>{t('settings.pipelineStatus')}</Text>
              {renderPipelineStatus()}
            </div>
            <Button
              type="primary"
              icon={<SyncOutlined />}
              onClick={handleSync}
              loading={runPipeline.isPending || pipelineStatus?.status === 'running'}
              disabled={pipelineStatus?.status === 'running'}
            >
              {t('settings.resync')}
            </Button>
          </div>

          {pipelineStatus?.stats && (
            <>
              <Divider style={{ margin: '12px 0' }} />
              <Descriptions column={3} size="small">
                <Descriptions.Item label={t('settings.statsDatabase')}>{pipelineStatus.stats.databases_processed}</Descriptions.Item>
                <Descriptions.Item label={t('settings.statsTables')}>{pipelineStatus.stats.tables_extracted}</Descriptions.Item>
                <Descriptions.Item label={t('settings.statsColumns')}>{pipelineStatus.stats.columns_extracted}</Descriptions.Item>
                <Descriptions.Item label={t('settings.statsForeignKeys')}>{pipelineStatus.stats.foreign_keys_extracted}</Descriptions.Item>
                <Descriptions.Item label={t('settings.statsNeo4jTables')}>{pipelineStatus.stats.neo4j_tables_written}</Descriptions.Item>
                <Descriptions.Item label={t('settings.statsMilvusTables')}>{pipelineStatus.stats.milvus_tables_written}</Descriptions.Item>
              </Descriptions>
            </>
          )}

          {pipelineStatus?.status === 'running' && (
            <Progress percent={50} status="active" showInfo={false} />
          )}
        </Space>
      </Card>

      <Card title={t('settings.llmConfig')} style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label={t('settings.queryMode')}>
            <Tag color={config?.llm.query_mode === 'plan' ? 'blue' : 'green'}>
              {config?.llm.query_mode === 'plan' ? t('settings.queryModePlan') : t('settings.queryModeFast')}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('settings.provider')}>
            <Tag>{config?.llm.provider}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('settings.model')}>{config?.llm.model}</Descriptions.Item>
          <Descriptions.Item label={t('settings.maxRetries')}>{config?.llm.max_sql_retries}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title={t('settings.retrievalConfig')} style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label={t('settings.topK')}>{config?.retrieval.search_top_k}</Descriptions.Item>
          <Descriptions.Item label={t('settings.expandFk')}>
            <Tag color={config?.retrieval.expand_fk ? 'green' : 'default'}>
              {config?.retrieval.expand_fk ? t('common.on') : t('common.off')}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('settings.semanticFilter')}>
            <Tag color={config?.retrieval.semantic_filter_enabled ? 'green' : 'default'}>
              {config?.retrieval.semantic_filter_enabled ? t('common.on') : t('common.off')}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('settings.filterThreshold')}>{config?.retrieval.semantic_filter_threshold}</Descriptions.Item>
          <Descriptions.Item label={t('settings.coreTables')} span={2}>
            {config?.retrieval.core_tables.map((tbl) => (
              <Tag key={tbl}>{tbl}</Tag>
            ))}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title={t('settings.embeddingConfig')}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label={t('settings.provider')}>{config?.embedding.provider}</Descriptions.Item>
          <Descriptions.Item label={t('settings.model')}>{config?.embedding.model}</Descriptions.Item>
          <Descriptions.Item label={t('settings.dimension')}>{config?.embedding.dimension}</Descriptions.Item>
        </Descriptions>
      </Card>
    </div>
  );
}
