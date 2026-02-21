import { useState, useEffect, useCallback } from 'react';
import {
  Table,
  Button,
  Space,
  Typography,
  Tag,
  Popconfirm,
  message,
  Input,
  Empty,
  Card,
  theme,
  Modal,
  Form,
} from 'antd';
import {
  DeleteOutlined,
  SearchOutlined,
  StarFilled,
  CodeOutlined,
  EditOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';

import { useAppStore } from '@/stores';
import { fewShotApi } from '@/api/fewShot';
import type { FewShotInfo, FewShotUpdateRequest } from '@/api/fewShot';

dayjs.extend(relativeTime);

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const DEFAULT_PAGE_SIZE = 20;

export default function FewShotPage() {
  const { t } = useTranslation();
  const { currentDatabase } = useAppStore();
  const { token } = theme.useToken();
  const [searchText, setSearchText] = useState('');
  const [loading, setLoading] = useState(false);
  const [examples, setExamples] = useState<FewShotInfo[]>([]);
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: DEFAULT_PAGE_SIZE,
  });

  // Edit modal state
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingExample, setEditingExample] = useState<FewShotInfo | null>(null);
  const [editForm] = Form.useForm();
  const [updating, setUpdating] = useState(false);

  const fetchExamples = useCallback(
    async (page = 1, pageSize = DEFAULT_PAGE_SIZE) => {
      if (!currentDatabase) return;

      setLoading(true);
      try {
        const offset = (page - 1) * pageSize;
        const response = await fewShotApi.list(currentDatabase, pageSize, offset);
        setExamples(response.items);
        setTotal(response.total);
        setPagination({ current: page, pageSize });
      } catch (error) {
        console.error('Failed to fetch few-shot examples:', error);
        message.error(t('fewShot.fetchFailed', 'Failed to load examples'));
      } finally {
        setLoading(false);
      }
    },
    [currentDatabase, t]
  );

  useEffect(() => {
    fetchExamples(1, pagination.pageSize);
  }, [currentDatabase]);

  const handleTableChange = (paginationConfig: TablePaginationConfig) => {
    const { current = 1, pageSize = DEFAULT_PAGE_SIZE } = paginationConfig;
    fetchExamples(current, pageSize);
  };

  const handleDelete = async (id: string) => {
    try {
      await fewShotApi.delete(id);
      message.success(t('fewShot.deleteSuccess', 'Example deleted'));
      // Refresh current page
      fetchExamples(pagination.current, pagination.pageSize);
    } catch (error) {
      console.error('Delete failed:', error);
      message.error(t('fewShot.deleteFailed', 'Failed to delete example'));
    }
  };

  const handleEdit = (record: FewShotInfo) => {
    setEditingExample(record);
    editForm.setFieldsValue({
      question: record.question,
      sql: record.sql,
      explanation: record.explanation || '',
    });
    setEditModalOpen(true);
  };

  const handleEditSubmit = async () => {
    if (!editingExample) return;

    try {
      const values = await editForm.validateFields();
      setUpdating(true);

      const updateData: FewShotUpdateRequest = {};
      if (values.question !== editingExample.question) {
        updateData.question = values.question;
      }
      if (values.sql !== editingExample.sql) {
        updateData.sql = values.sql;
      }
      if ((values.explanation || '') !== (editingExample.explanation || '')) {
        updateData.explanation = values.explanation || undefined;
      }

      // Only update if there are changes
      if (Object.keys(updateData).length > 0) {
        await fewShotApi.update(editingExample.id, updateData);
        message.success(t('fewShot.updateSuccess', 'Example updated'));
        fetchExamples(pagination.current, pagination.pageSize);
      }

      setEditModalOpen(false);
      setEditingExample(null);
    } catch (error) {
      console.error('Update failed:', error);
      message.error(t('fewShot.updateFailed', 'Failed to update example'));
    } finally {
      setUpdating(false);
    }
  };

  // Client-side filter for search (within current page)
  const filteredExamples = searchText
    ? examples.filter(
        (example) =>
          example.question.toLowerCase().includes(searchText.toLowerCase()) ||
          example.sql.toLowerCase().includes(searchText.toLowerCase())
      )
    : examples;

  const columns: ColumnsType<FewShotInfo> = [
    {
      title: t('fewShot.question', 'Question'),
      dataIndex: 'question',
      key: 'question',
      width: 380,
      ellipsis: true,
      render: (text: string) => (
        <Text style={{ display: 'inline-block', width: '100%' }} ellipsis={{ tooltip: text }}>
          {text}
        </Text>
      ),
    },
    {
      title: t('fewShot.tablesUsed', 'Tables'),
      dataIndex: 'tables_used',
      key: 'tables_used',
      width: 320,
      render: (tables: string[]) =>
        tables && tables.length > 0 ? (
        <Space wrap size={4}>
          {tables?.slice(0, 3).map((table) => (
            <Tag key={table} color="blue">
              {table}
            </Tag>
          ))}
          {tables?.length > 3 && <Tag>+{tables.length - 3}</Tag>}
        </Space>
        ) : (
          <Text type="secondary">-</Text>
        ),
    },
    {
      title: t('fewShot.createdAt', 'Created'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (time: string) => (
        <Text type="secondary">
          {new Intl.DateTimeFormat(undefined, {
            year: 'numeric',
            month: 'numeric',
            day: 'numeric',
            hour: 'numeric',
            minute: 'numeric',
          }).format(new Date(time))}
        </Text>
      ),
      sorter: (a, b) => dayjs(a.created_at).valueOf() - dayjs(b.created_at).valueOf(),
      defaultSortOrder: 'descend',
    },
    {
      title: t('common.actions', 'Actions'),
      key: 'actions',
      width: 110,
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
            aria-label={t('common.edit', 'Edit')}
          />
          <Popconfirm
            title={t('fewShot.deleteConfirm', 'Delete this example?')}
            onConfirm={() => handleDelete(record.id)}
            okText={t('common.delete', 'Delete')}
            cancelText={t('common.cancel', 'Cancel')}
          >
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              aria-label={t('common.delete', 'Delete')}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const expandedRowRender = (record: FewShotInfo) => (
    <Card size="small" style={{ background: token.colorFillQuaternary }}>
      <Space direction="vertical" style={{ width: '100%' }}>
        <div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {t('fewShot.sql', 'SQL')}:
          </Text>
          <pre
            style={{
              background: token.colorBgContainer,
              padding: 12,
              borderRadius: 6,
              overflow: 'auto',
              margin: '8px 0',
              fontSize: 13,
            }}
          >
            <code>{record.sql}</code>
          </pre>
        </div>
        {record.explanation && (
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('fewShot.explanation', 'Explanation')}:
            </Text>
            <Paragraph style={{ margin: '4px 0' }}>{record.explanation}</Paragraph>
          </div>
        )}
      </Space>
    </Card>
  );

  if (!currentDatabase) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          minHeight: 400,
        }}
      >
        <Empty
          image={<StarFilled style={{ fontSize: 48, color: token.colorTextQuaternary }} />}
          description={t('fewShot.selectDatabase', 'Please select a database first')}
        />
      </div>
    );
  }

  return (
    <div>
      <div
        style={{
          marginBottom: 16,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <Space>
          <Title level={4} style={{ margin: 0 }}>
            <StarFilled style={{ color: '#faad14', marginRight: 8 }} />
            {t('fewShot.title', 'Few-Shot Examples')}
          </Title>
          <Tag color="blue">{currentDatabase.toUpperCase()}</Tag>
          <Text type="secondary">
            ({t('common.total', { count: total, defaultValue: `${total} total` })})
          </Text>
        </Space>
        <Space>
          <Input
            placeholder={t('common.search', 'Search')}
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 200 }}
            allowClear
          />
          <Button
            icon={<ReloadOutlined />}
            onClick={() => fetchExamples(pagination.current, pagination.pageSize)}
          >
            {t('common.refresh', 'Refresh')}
          </Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={filteredExamples}
        rowKey="id"
        tableLayout="fixed"
        loading={loading}
        expandable={{
          expandedRowRender,
          expandedRowKeys,
          onExpandedRowsChange: (keys) => setExpandedRowKeys(keys as string[]),
          expandIcon: ({ expanded, onExpand, record }) => (
            <Button
              type="text"
              size="small"
              icon={<CodeOutlined />}
              onClick={(e) => onExpand(record, e)}
              style={{ color: expanded ? token.colorPrimary : undefined }}
            />
          ),
        }}
        pagination={{
          current: pagination.current,
          pageSize: pagination.pageSize,
          total: searchText ? filteredExamples.length : total,
          showSizeChanger: true,
          pageSizeOptions: ['10', '20', '50', '100'],
          showTotal: (totalCount) =>
            t('common.paginationTotal', {
              count: totalCount,
              defaultValue: `${totalCount} items`,
            }),
        }}
        onChange={handleTableChange}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('fewShot.noExamples', 'No examples saved yet')}
            />
          ),
        }}
      />

      {/* Edit Modal */}
      <Modal
        title={t('fewShot.editExample', 'Edit Example')}
        open={editModalOpen}
        onOk={handleEditSubmit}
        onCancel={() => {
          setEditModalOpen(false);
          setEditingExample(null);
        }}
        confirmLoading={updating}
        width={700}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="question"
            label={t('fewShot.question', 'Question')}
            rules={[{ required: true, message: t('fewShot.questionRequired', 'Question is required') }]}
          >
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item
            name="sql"
            label={t('fewShot.sql', 'SQL')}
            rules={[{ required: true, message: t('fewShot.sqlRequired', 'SQL is required') }]}
          >
            <TextArea
              rows={6}
              style={{ fontFamily: "'Fira Code', 'Monaco', monospace" }}
            />
          </Form.Item>
          <Form.Item name="explanation" label={t('fewShot.explanation', 'Explanation')}>
            <TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
