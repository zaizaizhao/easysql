import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Button, Space, Typography, Tag, Popconfirm, message, Input } from 'antd';
import { DeleteOutlined, MessageOutlined, SearchOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';

import { useSessions, useDeleteSession } from '@/hooks';
import type { SessionInfo } from '@/types';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

const { Title, Text } = Typography;

export default function HistoryPage() {
  const navigate = useNavigate();
  const [searchText, setSearchText] = useState('');
  
  const { data, isLoading, refetch } = useSessions();
  const deleteSession = useDeleteSession();

  const handleDelete = async (sessionId: string) => {
    try {
      await deleteSession.mutateAsync(sessionId);
      message.success('会话已删除');
    } catch {
      message.error('删除失败');
    }
  };

  const handleOpen = (sessionId: string) => {
    navigate(`/chat/${sessionId}`);
  };

  const filteredSessions = data?.sessions.filter((session) =>
    session.session_id.toLowerCase().includes(searchText.toLowerCase()) ||
    session.db_name?.toLowerCase().includes(searchText.toLowerCase())
  ) || [];

  const columns: ColumnsType<SessionInfo> = [
    {
      title: '数据库',
      dataIndex: 'db_name',
      key: 'db_name',
      width: 100,
      render: (dbName: string) => (
        <Tag color="blue">{dbName?.toUpperCase() || '-'}</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => {
        const statusMap: Record<string, { color: string; text: string }> = {
          completed: { color: 'success', text: '已完成' },
          awaiting_clarification: { color: 'warning', text: '待澄清' },
          processing: { color: 'processing', text: '处理中' },
          failed: { color: 'error', text: '失败' },
          pending: { color: 'default', text: '待处理' },
        };
        const config = statusMap[status] || { color: 'default', text: status };
        return <Tag color={config.color}>{config.text}</Tag>;
      },
    },
    {
      title: '消息数',
      dataIndex: 'question_count',
      key: 'question_count',
      width: 80,
      align: 'center',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (time: string) => (
        <Text type="secondary">{dayjs(time).fromNow()}</Text>
      ),
      sorter: (a, b) => dayjs(a.created_at).valueOf() - dayjs(b.created_at).valueOf(),
      defaultSortOrder: 'descend',
    },
    {
      title: '操作',
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
            打开
          </Button>
          <Popconfirm
            title="确定删除此会话？"
            onConfirm={() => handleDelete(record.session_id)}
            okText="删除"
            cancelText="取消"
          >
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={4} style={{ margin: 0 }}>历史会话</Title>
        <Space>
          <Input
            placeholder="搜索..."
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 200 }}
            allowClear
          />
          <Button onClick={() => refetch()}>刷新</Button>
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
          showTotal: (total) => `共 ${total} 条`,
        }}
      />
    </div>
  );
}
