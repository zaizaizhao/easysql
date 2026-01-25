import { useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Button, Tooltip, Divider, message, theme } from 'antd';
import {
  HistoryOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAppStore, useChatStore } from '@/stores';
import { SessionList } from './SessionList';
import { createSession } from '@/api';

const { Sider } = Layout;

export function Sidebar() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { sidebarCollapsed, toggleSidebar } = useAppStore();
  const { cacheCurrentSession, addNewSession } = useChatStore();
  const { token } = theme.useToken();

  const menuItems = [
    {
      key: '/history',
      icon: <HistoryOutlined />,
      label: t('nav.history'),
    },
    {
      key: '/settings',
      icon: <SettingOutlined />,
      label: t('nav.settings'),
    },
  ];

  const handleNewChat = async () => {
    cacheCurrentSession();
    try {
      const session = await createSession();
      addNewSession(session);
      navigate('/chat');
    } catch (error) {
      console.error('Failed to create session:', error);
      message.error(t('session.createError', 'Failed to create session'));
    }
  };

  return (
    <Sider
      trigger={null}
      collapsible
      collapsed={sidebarCollapsed}
      width={240}
      collapsedWidth={60}
      style={{
        background: token.colorBgContainer,
        borderRight: `1px solid ${token.colorBorder}`,
      }}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          padding: '8px',
          overflowY: 'auto',
          overflowX: 'hidden',
        }}
      >
        <div style={{ marginBottom: 8 }}>
          <Tooltip title={sidebarCollapsed ? t('nav.newChat') : ''} placement="right">
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleNewChat}
              block
              aria-label={t('nav.newChat')}
            >
              {!sidebarCollapsed && t('nav.newChat')}
            </Button>
          </Tooltip>
        </div>

        {!sidebarCollapsed && (
          <>
            <SessionList collapsed={sidebarCollapsed} />
            <Divider style={{ margin: '8px 0' }} />
          </>
        )}

        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ 
            background: 'transparent',
            border: 'none',
            flex: sidebarCollapsed ? 1 : 0,
          }}
        />

        <div style={{ marginTop: 'auto' }}>
          <Button
            type="text"
            icon={sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={toggleSidebar}
            block
            aria-label={sidebarCollapsed ? t('common.expand') : t('common.collapse')}
          />
        </div>
      </div>
    </Sider>
  );
}
