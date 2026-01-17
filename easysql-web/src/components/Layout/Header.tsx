import { Layout, Space, Typography } from 'antd';
import { DatabaseSwitcher, ThemeToggle } from '@/components/Common';

const { Header: AntHeader } = Layout;
const { Title } = Typography;

export function Header() {
  return (
    <AntHeader
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 24px',
        background: 'transparent',
        borderBottom: '1px solid var(--border-color)',
      }}
    >
      <Space>
        <Title level={4} style={{ margin: 0, color: 'var(--primary-color)' }}>
          🚀 EasySQL
        </Title>
      </Space>

      <Space size="middle">
        <DatabaseSwitcher />
        <ThemeToggle />
      </Space>
    </AntHeader>
  );
}
