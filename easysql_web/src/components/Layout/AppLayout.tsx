import { Outlet } from 'react-router-dom';
import { Layout } from 'antd';
import { Header } from './Header';
import { Sidebar } from './Sidebar';

const { Content } = Layout;

export function AppLayout() {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sidebar />
      <Layout>
        <Header />
        <Content
          style={{
            padding: 24,
            overflow: 'auto',
            background: 'var(--content-bg)',
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
