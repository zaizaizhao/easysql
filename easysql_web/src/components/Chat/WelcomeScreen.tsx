import { Typography, theme, Space } from 'antd';
import { DatabaseOutlined, MessageOutlined, BulbOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ChatInput } from './ChatInput';

const { Title, Text } = Typography;

interface WelcomeScreenProps {
  onSend: (message: string) => void;
}

export function WelcomeScreen({ onSend }: WelcomeScreenProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        padding: '0 24px',
        maxWidth: 800,
        margin: '0 auto',
        width: '100%',
      }}
    >
      <div style={{ marginBottom: 48, textAlign: 'center' }}>
        <div
          style={{
            width: 64,
            height: 64,
            background: token.colorPrimaryBg,
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 24px',
          }}
        >
          <DatabaseOutlined style={{ fontSize: 32, color: token.colorPrimary }} />
        </div>
        <Title level={2} style={{ marginBottom: 16 }}>
          {t('welcome.title', 'EasySQL Assistant')}
        </Title>
        <Text type="secondary" style={{ fontSize: 16 }}>
          {t('welcome.subtitle', 'Ask questions about your data in natural language')}
        </Text>
      </div>

      <div style={{ width: '100%', marginBottom: 48 }}>
        <ChatInput onSend={onSend} />
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: 16,
          width: '100%',
        }}
      >
        <FeatureCard
          icon={<MessageOutlined />}
          title={t('welcome.feature1.title', 'Natural Language')}
          description={t('welcome.feature1.desc', 'Query database using plain English')}
        />
        <FeatureCard
          icon={<DatabaseOutlined />}
          title={t('welcome.feature2.title', 'Smart Context')}
          description={t('welcome.feature2.desc', 'Automatically finds relevant tables')}
        />
        <FeatureCard
          icon={<BulbOutlined />}
          title={t('welcome.feature3.title', 'Auto-Correction')}
          description={t('welcome.feature3.desc', 'Fixes SQL errors automatically')}
        />
      </div>
    </div>
  );
}

function FeatureCard({ icon, title, description }: { icon: React.ReactNode; title: string; description: string }) {
  const { token } = theme.useToken();
  return (
    <div
      style={{
        padding: 24,
        background: token.colorFillQuaternary,
        borderRadius: 12,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
    >
      <div style={{ fontSize: 24, color: token.colorPrimary }}>{icon}</div>
      <div style={{ fontWeight: 600, fontSize: 16 }}>{title}</div>
      <div style={{ color: token.colorTextSecondary }}>{description}</div>
    </div>
  );
}
