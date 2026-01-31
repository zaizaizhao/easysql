import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Button, Space, Typography, Tag, Popconfirm, message, Input } from 'antd';
import { DeleteOutlined, MessageOutlined, SearchOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';

import { useSessions, useDeleteSession } from '@/hooks';
import type { SessionInfo } from '@/types';

dayjs.extend(relativeTime);

const { Title, Text } = Typography;

export default function HistoryPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchText, setSearchText] = useState('');
  
  const { data, isLoading, refetch } = useSessions();
  const deleteSession = useDeleteSession();

  const handleDelete = async (sessionId: string) => {
    try {
      await deleteSession.mutateAsync(sessionId);
      message.success(t('history.deleteSuccess'));
    } catch {
      message.error(t('history.deleteFailed'));
    }
  };

  const handleOpen = (sessionId: string) => {
    navigate(`/chat/${sessionId}`);
  };

  const filteredSessions = data?.sessions.filter((session) =>
    session.session_id.toLowerCase().includes(searchText.toLowerCase()) ||
    session.db_name?.toLowerCase().includes(searchText.toLowerCase()) ||
    session.title?.toLowerCase().includes(searchText.toLowerCase())
  ) || [];

  const columns: ColumnsType<SessionInfo> = [
    {
      title: t('history.database'),
      dataIndex: 'db_name',
      key: 'db_name',
      width: 100,
      render: (dbName: string) => (
        <Tag color="blue">{dbName?.toUpperCase() || '-'}</Tag>
      ),
    },
    {
      title: t('history.firstQuestion'),
      dataIndex: 'title',
      key: 'title',
      width: 260,
      ellipsis: true,
      render: (title?: string) => title || '-',
    },
    {
      title: t('history.status'),
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => {
        const statusMap: Record<string, { color: string; text: string }> = {
          completed: { color: 'success', text: t('history.statusCompleted') },
          awaiting_clarification: { color: 'warning', text: t('history.statusAwaitingClarification') },
          processing: { color: 'processing', text: t('history.statusProcessing') },
          failed: { color: 'error', text: t('history.statusFailed') },
          pending: { color: 'default', text: t('history.statusPending') },
        };
        const config = statusMap[status] || { color: 'default', text: status };
        return <Tag color={config.color}>{config.text}</Tag>;
      },
    },
    {
      title: t('history.messageCount'),
      dataIndex: 'question_count',
      key: 'question_count',
      width: 80,
      align: 'center',
    },
    {
      title: t('history.createdAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (time: string) => (
        <Text type="secondary">
          {new Intl.DateTimeFormat(undefined, { 
            year: 'numeric', 
            month: 'numeric', 
            day: 'numeric', 
            hour: 'numeric', 
            minute: 'numeric' 
          }).format(new Date(time))}
        </Text>
      ),
      sorter: (a, b) => dayjs(a.created_at).valueOf() - dayjs(b.created_at).valueOf(),
      defaultSortOrder: 'descend',
    },
    {
      title: t('history.actions'),
      key: 'actions',
      width: 120,
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<MessageOutlined />}
            onClick={() => handleOpen(record.session_id)}
          >
            {t('common.open')}
          </Button>
          <Popconfirm
            title={t('history.deleteConfirm')}
            onConfirm={() => handleDelete(record.session_id)}
            okText={t('common.delete')}
            cancelText={t('common.cancel')}
          >
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              aria-label={t('common.delete')}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={4} style={{ margin: 0 }}>{t('history.title')}</Title>
        <Space>
          <Input
            placeholder={t('common.search')}
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 200 }}
            allowClear
          />
          <Button onClick={() => refetch()}>{t('common.refresh')}</Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={filteredSessions}
        rowKey="session_id"
        loading={isLoading}
        pagination={{
          pageSize: 20,
          showSizeChanger: true,
          showTotal: (total) => t('common.total', { count: total }),
        }}
      />
    </div>
  );
}
