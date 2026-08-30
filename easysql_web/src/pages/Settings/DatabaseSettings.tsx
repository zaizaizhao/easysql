import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { TableColumnsType } from 'antd';
import {
  ApiOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  ClusterOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  EditOutlined,
  LoadingOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

import {
  useDeleteManagedDatabase,
  useFederationStatus,
  useManagedDatabases,
  useReplaceManagedDatabases,
  useTestManagedDatabase,
} from '@/hooks';
import { useAppStore } from '@/stores';
import type { DatabaseConfigInput, DatabaseInfo } from '@/types';

const { Text } = Typography;

const DATABASE_TYPE_OPTIONS = [
  { value: 'postgresql', label: 'PostgreSQL' },
  { value: 'mysql', label: 'MySQL' },
  { value: 'oracle', label: 'Oracle' },
  { value: 'sqlserver', label: 'SQL Server' },
];

const DEFAULT_PORTS: Record<DatabaseConfigInput['type'], number> = {
  postgresql: 5432,
  mysql: 3306,
  oracle: 1521,
  sqlserver: 1433,
};

function toInput(database: DatabaseInfo): DatabaseConfigInput {
  return {
    name: database.name,
    type: database.type as DatabaseConfigInput['type'],
    host: database.host,
    port: database.port,
    user: database.user || '',
    database: database.database,
    schema: database.schema,
    system_type: database.system_type || 'UNKNOWN',
    description: database.description || '',
  };
}

export function DatabaseSettings() {
  const { t } = useTranslation();
  const { data, isLoading } = useManagedDatabases();
  const replaceDatabases = useReplaceManagedDatabases();
  const deleteDatabase = useDeleteManagedDatabase();
  const testDatabase = useTestManagedDatabase();
  const [form] = Form.useForm<DatabaseConfigInput>();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingName, setEditingName] = useState<string | null>(null);
  const [databases, setDatabases] = useState<DatabaseInfo[]>([]);
  const { selectedDatabases } = useAppStore();
  const isMultiDatabase = selectedDatabases.length > 1;
  const {
    data: federationStatus,
    isFetching: isStatusFetching,
    isError: isStatusError,
    refetch: refetchFederationStatus,
  } = useFederationStatus(selectedDatabases);
  const selectedDatabaseSet = useMemo(() => new Set(selectedDatabases), [selectedDatabases]);
  const dblinkStatusByName = useMemo(
    () => new Map(
      (federationStatus?.databases || []).map((database) => [database.name, database]),
    ),
    [federationStatus],
  );

  useEffect(() => {
    if (data?.databases) {
      setDatabases(data.databases);
    }
  }, [data]);

  const openCreate = () => {
    setEditingName(null);
    form.setFieldsValue({
      name: '',
      type: 'postgresql',
      host: 'localhost',
      port: 5432,
      user: 'postgres',
      password: '',
      database: '',
      schema: 'public',
      system_type: 'UNKNOWN',
      description: '',
    });
    setIsModalOpen(true);
  };

  const openEdit = (database: DatabaseInfo) => {
    setEditingName(database.name);
    form.setFieldsValue({ ...toInput(database), password: '' });
    setIsModalOpen(true);
  };

  const buildReplacement = (nextDatabase: DatabaseConfigInput): DatabaseConfigInput[] => {
    const normalized: DatabaseConfigInput = {
      ...nextDatabase,
      name: nextDatabase.name.trim().toLowerCase(),
      password: nextDatabase.password?.trim() || undefined,
      schema: nextDatabase.schema?.trim() || undefined,
    };
    const current = databases.map(toInput);
    if (!editingName) {
      return [...current, normalized];
    }
    return current.map((item) => (item.name === editingName ? normalized : item));
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      const result = await replaceDatabases.mutateAsync(buildReplacement(values));
      setDatabases(result.databases);
      setIsModalOpen(false);
      message.success(t('settings.databases.saveSuccess'));
    } catch (error) {
      if ((error as { errorFields?: unknown }).errorFields) return;
      message.error((error as Error).message || t('settings.databases.saveFailed'));
    }
  };

  const handleTest = async () => {
    try {
      const values = await form.validateFields();
      const result = await testDatabase.mutateAsync({
        ...values,
        password: values.password?.trim() || undefined,
      });
      if (result.success) {
        message.success(result.message);
      } else {
        message.error(result.message);
      }
    } catch (error) {
      if ((error as { errorFields?: unknown }).errorFields) return;
      message.error((error as Error).message || t('settings.databases.testFailed'));
    }
  };

  const handleDelete = async (name: string) => {
    try {
      const result = await deleteDatabase.mutateAsync(name);
      setDatabases(result.databases);
      message.success(t('settings.databases.deleteSuccess'));
    } catch (error) {
      message.error((error as Error).message || t('settings.databases.deleteFailed'));
    }
  };

  const columns: TableColumnsType<DatabaseInfo> = useMemo(
    () => [
      {
        title: t('settings.databases.logicalName'),
        dataIndex: 'name',
        key: 'name',
        render: (name: string, record) => (
          <Space>
            <DatabaseOutlined style={{ color: '#1677ff' }} />
            <Text strong>{name.toUpperCase()}</Text>
            {record.system_type && record.system_type !== 'UNKNOWN' && (
              <Tag>{record.system_type.toUpperCase()}</Tag>
            )}
          </Space>
        ),
      },
      {
        title: t('settings.databases.connection'),
        key: 'connection',
        render: (_, record) => (
          <div>
            <div>{record.type} · {record.host}:{record.port}</div>
            <Text type="secondary">
              {record.database}{record.schema ? ` / ${record.schema}` : ''}
            </Text>
          </div>
        ),
      },
      {
        title: t('settings.databases.modeStatus'),
        key: 'dblink',
        render: (_, record) => {
          const selected = selectedDatabaseSet.has(record.name);
          if (!selected) {
            return <Tag>{t('settings.databases.notSelected')}</Tag>;
          }
          if (!isMultiDatabase) {
            return (
              <div>
                <Tag color="blue" icon={<DatabaseOutlined />}>
                  {t('database.singleMode')}
                </Tag>
                <div><Text type="secondary">{t('database.singleModeDescription')}</Text></div>
              </div>
            );
          }
          if (record.type !== 'postgresql') {
            return <Tag color="error">{t('settings.databases.singleOnly')}</Tag>;
          }
          const dblinkStatus = dblinkStatusByName.get(record.name);
          if (!dblinkStatus && isStatusFetching) {
            return (
              <Tag color="processing" icon={<LoadingOutlined spin />}>
                {t('database.dblinkChecking')}
              </Tag>
            );
          }
          const ready = dblinkStatus?.status === 'ready' && !isStatusError;
          return (
            <div>
              <Tag
                color={ready ? 'success' : 'error'}
                icon={ready ? <CheckCircleFilled /> : <CloseCircleFilled />}
              >
                {ready ? t('database.dblinkReady') : t('database.dblinkUnavailable')}
              </Tag>
              <div>
                <Text type="secondary">
                  {t('settings.databases.connectionAlias')}: {' '}
                  <Text code>{dblinkStatus?.connection_name || record.dblink_connection_name}</Text>
                </Text>
              </div>
              {!ready && dblinkStatus?.reason && (
                <div>
                  <Text type="danger">{t(`database.statusReason.${dblinkStatus.reason}`)}</Text>
                </div>
              )}
            </div>
          );
        },
      },
      {
        title: t('settings.databases.description'),
        dataIndex: 'description',
        key: 'description',
        ellipsis: true,
        render: (value?: string) => value || <Text type="secondary">—</Text>,
      },
      {
        title: t('settings.databases.actions'),
        key: 'actions',
        width: 140,
        render: (_, record) => (
          <Space>
            <Button type="text" icon={<EditOutlined />} onClick={() => openEdit(record)} />
            <Popconfirm
              title={t('settings.databases.deleteConfirm', { name: record.name.toUpperCase() })}
              onConfirm={() => void handleDelete(record.name)}
            >
              <Button danger type="text" icon={<DeleteOutlined />} />
            </Popconfirm>
          </Space>
        ),
      },
    ],
    // Translation changes recreate the columns; database mutations are stable hook objects.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      t,
      databases,
      selectedDatabaseSet,
      isMultiDatabase,
      dblinkStatusByName,
      isStatusFetching,
      isStatusError,
    ],
  );

  const multiReady = federationStatus?.status === 'ready' && !isStatusError;
  const modeAlertType = !isMultiDatabase
    ? 'info'
    : !federationStatus && isStatusFetching
      ? 'info'
      : multiReady
        ? 'success'
        : 'error';

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Alert
        type={modeAlertType}
        showIcon
        icon={isMultiDatabase ? <ClusterOutlined /> : <DatabaseOutlined />}
        title={
          isMultiDatabase
            ? multiReady
              ? t('settings.databases.multiModeReadyTitle', { count: selectedDatabases.length })
              : !federationStatus && isStatusFetching
                ? t('settings.databases.multiModeCheckingTitle', { count: selectedDatabases.length })
                : t('settings.databases.multiModeUnavailableTitle', { count: selectedDatabases.length })
            : t('settings.databases.singleModeTitle')
        }
        description={
          isMultiDatabase
            ? multiReady
              ? t('settings.databases.multiModeReadyDescription')
              : !federationStatus && isStatusFetching
                ? t('settings.databases.multiModeCheckingDescription')
                : t('settings.databases.multiModeUnavailableDescription')
            : t('settings.databases.singleModeDescription')
        }
        action={isMultiDatabase ? (
          <Button
            size="small"
            icon={<ReloadOutlined />}
            loading={isStatusFetching}
            onClick={() => void refetchFederationStatus()}
          >
            {t('settings.databases.recheckDblink')}
          </Button>
        ) : undefined}
      />
      <Card
        className="settings-panel-card"
        title={t('settings.databases.title')}
        extra={(
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            {t('settings.databases.add')}
          </Button>
        )}
      >
        <Table
          rowKey="name"
          loading={isLoading}
          columns={columns}
          dataSource={databases}
          pagination={false}
          locale={{ emptyText: t('settings.databases.empty') }}
          scroll={{ x: 900 }}
        />
      </Card>

      <Modal
        title={
          editingName
            ? t('settings.databases.editTitle', { name: editingName.toUpperCase() })
            : t('settings.databases.addTitle')
        }
        open={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        onOk={() => void handleSave()}
        confirmLoading={replaceDatabases.isPending}
        width={760}
        destroyOnHidden
        footer={(_, { OkBtn, CancelBtn }) => (
          <Space style={{ width: '100%', justifyContent: 'space-between' }}>
            <Button
              icon={<ApiOutlined />}
              onClick={() => void handleTest()}
              loading={testDatabase.isPending}
            >
              {t('settings.databases.test')}
            </Button>
            <Space>
              <CancelBtn />
              <OkBtn />
            </Space>
          </Space>
        )}
      >
        <Form form={form} layout="vertical" preserve={false}>
          <div className="database-form-grid">
            <Form.Item
              name="name"
              label={t('settings.databases.logicalName')}
              rules={[
                { required: true },
                { pattern: /^[A-Za-z][A-Za-z0-9_]{0,63}$/, message: t('settings.databases.nameRule') },
              ]}
            >
              <Input disabled={Boolean(editingName)} placeholder="emr" />
            </Form.Item>
            <Form.Item name="type" label={t('settings.databases.type')} rules={[{ required: true }]}>
              <Select
                options={DATABASE_TYPE_OPTIONS}
                onChange={(type: DatabaseConfigInput['type']) => {
                  form.setFieldValue('port', DEFAULT_PORTS[type]);
                  if (type === 'postgresql' && !form.getFieldValue('schema')) {
                    form.setFieldValue('schema', 'public');
                  }
                }}
              />
            </Form.Item>
            <Form.Item name="system_type" label={t('settings.databases.systemType')}>
              <Input placeholder="EMR / PMS / RVS" />
            </Form.Item>
            <Form.Item name="host" label={t('settings.databases.host')} rules={[{ required: true }]}>
              <Input placeholder="127.0.0.1" />
            </Form.Item>
            <Form.Item name="port" label={t('settings.databases.port')} rules={[{ required: true }]}>
              <InputNumber min={1} max={65535} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="database" label={t('settings.databases.database')} rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="schema" label={t('settings.databases.schema')}>
              <Input placeholder="public" />
            </Form.Item>
            <Form.Item name="user" label={t('settings.databases.user')} rules={[{ required: true }]}>
              <Input autoComplete="username" />
            </Form.Item>
            <Form.Item
              name="password"
              label={t('settings.databases.password')}
              extra={editingName ? t('settings.databases.passwordKeep') : undefined}
            >
              <Input.Password autoComplete="new-password" />
            </Form.Item>
          </div>
          <Form.Item name="description" label={t('settings.databases.description')}>
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
