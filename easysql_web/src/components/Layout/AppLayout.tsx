import { Outlet } from 'react-router-dom';
import { Layout, theme } from 'antd';
import { Header } from './Header';
import { Sidebar } from './Sidebar';

const { Content } = Layout;

export function AppLayout() {
  const { token } = theme.useToken();
  return (
    <Layout style={{ height: '100vh', overflow: 'hidden' }}>
      <Sidebar />
      <Layout>
        <Header />
        <Content
          style={{
            padding: 24,
            overflow: 'hidden',
            background: token.colorBgLayout,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}
