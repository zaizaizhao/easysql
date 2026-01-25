import { useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Button, Tooltip, Divider, theme, Typography } from 'antd';
import {
  HistoryOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlusOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAppStore, useChatStore } from '@/stores';
import { SessionList } from './SessionList';

const { Sider } = Layout;
const { Title } = Typography;

export function Sidebar() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { sidebarCollapsed, toggleSidebar } = useAppStore();
  const { cacheCurrentSession, setSessionId } = useChatStore();
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

  const handleNewChat = () => {
    cacheCurrentSession();
    setSessionId(null);
    navigate('/chat');
  };

  return (
    <Sider
      trigger={null}
      collapsible
      collapsed={sidebarCollapsed}
      width={260}
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
          overflow: 'hidden',
        }}
      >
        <div style={{ padding: '16px 12px 12px' }}>
          {!sidebarCollapsed && (
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: 8, 
              marginBottom: 16, 
              paddingLeft: 4 
            }}>
              <div style={{
                width: 24,
                height: 24,
                background: token.colorPrimary,
                borderRadius: 4,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                <DatabaseOutlined style={{ color: '#fff', fontSize: 14 }} />
              </div>
              <Title level={5} style={{ margin: 0, fontWeight: 600 }}>EasySQL</Title>
            </div>
          )}
          
          <Tooltip title={sidebarCollapsed ? t('nav.newChat') : ''} placement="right">
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleNewChat}
              block
              size="large"
              style={{ 
                height: 40,
                borderRadius: 8,
                display: 'flex',
                alignItems: 'center',
                justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
                paddingLeft: sidebarCollapsed ? undefined : 16,
              }}
            >
              {!sidebarCollapsed && t('nav.newChat')}
            </Button>
          </Tooltip>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', paddingBottom: 8 }}>
          <SessionList collapsed={sidebarCollapsed} />
        </div>

        <div style={{ padding: 8, borderTop: `1px solid ${token.colorBorderSecondary}` }}>
          <Menu
            mode="inline"
            selectedKeys={[location.pathname]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
            style={{ 
              background: 'transparent',
              border: 'none',
            }}
          />
          
          <Divider style={{ margin: '8px 0' }} />
          
          <Button
            type="text"
            icon={sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={toggleSidebar}
            block
            style={{ color: token.colorTextSecondary }}
            aria-label={sidebarCollapsed ? t('common.expand') : t('common.collapse')}
          />
        </div>
      </div>
    </Sider>
  );
}
