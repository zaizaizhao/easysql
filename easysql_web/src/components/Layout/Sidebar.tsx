import { useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Button, Tooltip } from 'antd';
import {
  MessageOutlined,
  HistoryOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAppStore, useChatStore } from '@/stores';

const { Sider } = Layout;

export function Sidebar() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { sidebarCollapsed, toggleSidebar } = useAppStore();
  const { clearChat } = useChatStore();

  const menuItems = [
    {
      key: '/chat',
      icon: <MessageOutlined />,
      label: t('nav.chat'),
    },
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

  const handleNewChat = () => {
    clearChat();
    navigate('/chat');
  };

  return (
    <Sider
      trigger={null}
      collapsible
      collapsed={sidebarCollapsed}
      width={200}
      collapsedWidth={60}
      style={{
        background: 'var(--sider-bg)',
        borderRight: '1px solid var(--border-color)',
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
        <div style={{ marginBottom: 16 }}>
          <Tooltip title={sidebarCollapsed ? t('nav.newChat') : ''} placement="right">
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleNewChat}
              block
            >
              {!sidebarCollapsed && t('nav.newChat')}
            </Button>
          </Tooltip>
        </div>

        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ 
            background: 'transparent',
            border: 'none',
            flex: 1,
          }}
        />

        <Button
          type="text"
          icon={sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          onClick={toggleSidebar}
          style={{ marginTop: 'auto' }}
        />
      </div>
    </Sider>
  );
}
