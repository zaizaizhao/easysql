import { useEffect } from 'react';
import { Select, Typography, Space, Tooltip, Tag, message } from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
  ClusterOutlined,
  DatabaseOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useDatabases, useFederationStatus } from '@/hooks';
import { useAppStore, useChatStore } from '@/stores';

const { Text } = Typography;

export function DatabaseSwitcher() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data, isLoading } = useDatabases();
  const {
    currentDatabase,
    selectedDatabases,
    setSelectedDatabases,
    setDatabases,
  } = useAppStore();
  const isMultiDatabase = selectedDatabases.length > 1;
  const {
    data: federationStatus,
    isFetching: isStatusFetching,
    isError: isStatusError,
  } = useFederationStatus(selectedDatabases);

  useEffect(() => {
    if (data?.databases) {
      setDatabases(data.databases);
      const available = new Set(data.databases.map((database) => database.name));
      const validSelection = selectedDatabases.filter((name) => available.has(name));
      if (validSelection.length === 0 && data.databases.length > 0) {
        validSelection.push(
          currentDatabase && available.has(currentDatabase)
            ? currentDatabase
            : data.databases[0].name,
        );
      }
      if (validSelection.join('|') !== selectedDatabases.join('|')) {
        setSelectedDatabases(validSelection);
      }
    }
  }, [data, currentDatabase, selectedDatabases, setSelectedDatabases, setDatabases]);

  const options = data?.databases.map((db) => ({
    value: db.name,
    label: (
      <Space>
        <DatabaseOutlined />
        <span>{db.name.toUpperCase()}</span>
        {db.description && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            ({db.description})
          </Text>
        )}
      </Space>
    ),
  })) || [];

  const handleSelectionChange = (values: string[]) => {
    const selected = (data?.databases || []).filter((database) => values.includes(database.name));
    if (values.length > 1 && selected.some((database) => database.type !== 'postgresql')) {
      message.warning(t('database.multiPostgresOnly'));
      return;
    }
    const chat = useChatStore.getState();
    if (chat.sessionId && values.join('|') !== selectedDatabases.join('|')) {
      chat.cacheCurrentSession();
      chat.clearChat();
      navigate('/chat');
      message.info(t('database.newSessionOnChange'));
    }
    setSelectedDatabases(values);
  };

  const renderModeTag = () => {
    if (!isMultiDatabase) {
      return (
        <Tooltip title={t('database.singleModeDescription')}>
          <Tag color="blue" icon={<DatabaseOutlined />} style={{ marginInlineEnd: 0 }}>
            {t('database.singleMode')}
          </Tag>
        </Tooltip>
      );
    }

    if (!federationStatus && isStatusFetching) {
      return (
        <Tooltip title={t('database.dblinkCheckingDescription')}>
          <Tag color="processing" icon={<LoadingOutlined spin />} style={{ marginInlineEnd: 0 }}>
            {t('database.dblinkChecking')}
          </Tag>
        </Tooltip>
      );
    }

    const ready = federationStatus?.status === 'ready' && !isStatusError;
    const failedDatabases = federationStatus?.databases.filter(
      (database) => database.status === 'unavailable',
    ) || [];
    const tooltip = ready ? (
      <div>
        <div>{t('database.dblinkReadyDescription')}</div>
        {federationStatus?.databases.map((database) => (
          <div key={database.name}>
            {database.name.toUpperCase()} · {database.routes.length} {t('database.routesReady')}
          </div>
        ))}
      </div>
    ) : (
      <div>
        <div>{t('database.dblinkUnavailableDescription')}</div>
        {failedDatabases.map((database) => (
          <div key={database.name}>
            {database.name.toUpperCase()} · {t(`database.statusReason.${database.reason}`)}
          </div>
        ))}
      </div>
    );

    return (
      <Tooltip title={tooltip}>
        <Tag
          color={ready ? 'success' : 'error'}
          icon={ready ? <CheckCircleFilled /> : <CloseCircleFilled />}
          style={{ marginInlineEnd: 0 }}
        >
          {ready ? t('database.dblinkReady') : t('database.dblinkUnavailable')}
        </Tag>
      </Tooltip>
    );
  };

  return (
    <Space size={4}>
      <Tooltip
        title={
          isMultiDatabase
            ? t('database.multiSelected', { count: selectedDatabases.length })
            : t('database.singleSelected')
        }
      >
        {isMultiDatabase ? (
          <ClusterOutlined style={{ color: '#722ed1', fontSize: 17 }} />
        ) : (
          <DatabaseOutlined />
        )}
      </Tooltip>
      <Select
        mode="multiple"
        value={selectedDatabases}
        onChange={handleSelectionChange}
        options={options}
        loading={isLoading}
        placeholder={t('database.select')}
        style={{ minWidth: 220, maxWidth: 360 }}
        variant="borderless"
        labelRender={({ value }) => String(value).toUpperCase()}
        maxTagCount={2}
        maxTagPlaceholder={(omitted) => (
          <Tag color="purple">+{omitted.length}</Tag>
        )}
      />
      {selectedDatabases.length > 0 && renderModeTag()}
    </Space>
  );
}
