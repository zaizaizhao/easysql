import { Card, Descriptions, Tag, Typography, Divider, Button, Space, Spin, Progress, message } from 'antd';
import { SyncOutlined, CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

import { useConfig, usePipelineStatus, useRunPipeline } from '@/hooks';

const { Title, Text } = Typography;

export default function SettingsPage() {
  const { data: config, isLoading: configLoading } = useConfig();
  const { data: pipelineStatus, isLoading: statusLoading } = usePipelineStatus();
  const runPipeline = useRunPipeline();

  const handleSync = async () => {
    try {
      await runPipeline.mutateAsync({});
      message.success('Pipeline 已启动');
    } catch {
      message.error('启动失败');
    }
  };

  const renderPipelineStatus = () => {
    if (statusLoading) return <Spin size="small" />;
    if (!pipelineStatus) return <Text type="secondary">未知</Text>;

    const statusConfig: Record<string, { icon: React.ReactNode; color: string; text: string }> = {
      idle: { icon: <ClockCircleOutlined />, color: 'default', text: '空闲' },
      running: { icon: <SyncOutlined spin />, color: 'processing', text: '运行中' },
      completed: { icon: <CheckCircleOutlined />, color: 'success', text: '已完成' },
      failed: { icon: <CloseCircleOutlined />, color: 'error', text: '失败' },
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
      <Title level={4}>系统设置</Title>

      <Card title="Schema 同步" style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <Text strong>Pipeline 状态：</Text>
              {renderPipelineStatus()}
            </div>
            <Button
              type="primary"
              icon={<SyncOutlined />}
              onClick={handleSync}
              loading={runPipeline.isPending || pipelineStatus?.status === 'running'}
              disabled={pipelineStatus?.status === 'running'}
            >
              重新同步
            </Button>
          </div>

          {pipelineStatus?.stats && (
            <>
              <Divider style={{ margin: '12px 0' }} />
              <Descriptions column={3} size="small">
                <Descriptions.Item label="数据库">{pipelineStatus.stats.databases_processed}</Descriptions.Item>
                <Descriptions.Item label="表">{pipelineStatus.stats.tables_extracted}</Descriptions.Item>
                <Descriptions.Item label="列">{pipelineStatus.stats.columns_extracted}</Descriptions.Item>
                <Descriptions.Item label="外键">{pipelineStatus.stats.foreign_keys_extracted}</Descriptions.Item>
                <Descriptions.Item label="Neo4j 表">{pipelineStatus.stats.neo4j_tables_written}</Descriptions.Item>
                <Descriptions.Item label="Milvus 表">{pipelineStatus.stats.milvus_tables_written}</Descriptions.Item>
              </Descriptions>
            </>
          )}

          {pipelineStatus?.status === 'running' && (
            <Progress percent={50} status="active" showInfo={false} />
          )}
        </Space>
      </Card>

      <Card title="LLM 配置" style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="查询模式">
            <Tag color={config?.llm.query_mode === 'plan' ? 'blue' : 'green'}>
              {config?.llm.query_mode === 'plan' ? 'Plan (交互式)' : 'Fast (直接)'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Provider">
            <Tag>{config?.llm.provider}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="模型">{config?.llm.model}</Descriptions.Item>
          <Descriptions.Item label="最大重试次数">{config?.llm.max_sql_retries}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="检索配置" style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="Top-K">{config?.retrieval.search_top_k}</Descriptions.Item>
          <Descriptions.Item label="外键扩展">
            <Tag color={config?.retrieval.expand_fk ? 'green' : 'default'}>
              {config?.retrieval.expand_fk ? '开启' : '关闭'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="语义过滤">
            <Tag color={config?.retrieval.semantic_filter_enabled ? 'green' : 'default'}>
              {config?.retrieval.semantic_filter_enabled ? '开启' : '关闭'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="过滤阈值">{config?.retrieval.semantic_filter_threshold}</Descriptions.Item>
          <Descriptions.Item label="核心表" span={2}>
            {config?.retrieval.core_tables.map((t) => (
              <Tag key={t}>{t}</Tag>
            ))}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="Embedding 配置">
        <Descriptions column={2} size="small">
          <Descriptions.Item label="Provider">{config?.embedding.provider}</Descriptions.Item>
          <Descriptions.Item label="模型">{config?.embedding.model}</Descriptions.Item>
          <Descriptions.Item label="维度">{config?.embedding.dimension}</Descriptions.Item>
        </Descriptions>
      </Card>
    </div>
  );
}
