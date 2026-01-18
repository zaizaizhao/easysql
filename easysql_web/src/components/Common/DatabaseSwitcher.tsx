import { useEffect } from 'react';
import { Select, Typography, Space } from 'antd';
import { DatabaseOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useDatabases } from '@/hooks';
import { useAppStore } from '@/stores';

const { Text } = Typography;

export function DatabaseSwitcher() {
  const { t } = useTranslation();
  const { data, isLoading } = useDatabases();
  const { currentDatabase, setCurrentDatabase, setDatabases } = useAppStore();

  useEffect(() => {
    if (data?.databases) {
      setDatabases(data.databases);
      if (!currentDatabase && data.databases.length > 0) {
        setCurrentDatabase(data.databases[0].name);
      }
    }
  }, [data, currentDatabase, setCurrentDatabase, setDatabases]);

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

  return (
    <Select
      value={currentDatabase}
      onChange={setCurrentDatabase}
      options={options}
      loading={isLoading}
      placeholder={t('database.select')}
      style={{ minWidth: 180 }}
      variant="borderless"
    />
  );
}
