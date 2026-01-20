import { Layout, Space, Typography, theme } from 'antd';
import { DatabaseSwitcher, ThemeToggle, LanguageSwitcher } from '@/components/Common';

const { Header: AntHeader } = Layout;
const { Title } = Typography;

export function Header() {
  const { token } = theme.useToken();
  return (
    <AntHeader
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 24px',
        background: 'transparent',
        borderBottom: `1px solid ${token.colorBorder}`,
      }}
    >
      <Space>
        <Title level={4} style={{ margin: 0, color: token.colorPrimary }}>
          EasySQL
        </Title>
      </Space>

      <Space size="middle">
        <DatabaseSwitcher />
        <LanguageSwitcher />
        <ThemeToggle />
      </Space>
    </AntHeader>
  );
}
