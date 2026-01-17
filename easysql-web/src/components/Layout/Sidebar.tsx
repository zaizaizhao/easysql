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
import { useAppStore, useChatStore } from '@/stores';

const { Sider } = Layout;

const menuItems = [
  {
    key: '/chat',
    icon: <MessageOutlined />,
    label: '对话',
  },
  {
    key: '/history',
    icon: <HistoryOutlined />,
    label: '历史',
  },
  {
    key: '/settings',
    icon: <SettingOutlined />,
    label: '设置',
  },
];

export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { sidebarCollapsed, toggleSidebar } = useAppStore();
  const { clearChat } = useChatStore();

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
        }}
      >
        <div style={{ marginBottom: 16 }}>
          <Tooltip title={sidebarCollapsed ? '新建对话' : ''} placement="right">
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleNewChat}
              block
            >
              {!sidebarCollapsed && '新建对话'}
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
