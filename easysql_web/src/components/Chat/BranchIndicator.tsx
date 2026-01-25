import { Button, Space, Typography, theme } from 'antd';
import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '@/stores';

const { Text } = Typography;

interface BranchIndicatorProps {
  siblings: string[];
  currentIndex: number;
}

export function BranchIndicator({ siblings, currentIndex }: BranchIndicatorProps) {
  const { t } = useTranslation();
  const { switchBranch } = useChatStore();
  const { token } = theme.useToken();

  if (siblings.length <= 1) return null;

  const handlePrev = () => {
    if (currentIndex > 0) {
      switchBranch(siblings[currentIndex - 1]);
    }
  };

  const handleNext = () => {
    if (currentIndex < siblings.length - 1) {
      switchBranch(siblings[currentIndex + 1]);
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '4px 0',
        marginTop: 4,
      }}
    >
      <Space size={4}>
        <Button
          type="text"
          size="small"
          icon={<LeftOutlined />}
          onClick={handlePrev}
          disabled={currentIndex === 0}
          aria-label={t('chat.previousBranch')}
          style={{
            fontSize: 10,
            width: 20,
            height: 20,
            color: token.colorTextSecondary,
          }}
        />
        <Text
          type="secondary"
          style={{ fontSize: 11, minWidth: 40, textAlign: 'center' }}
        >
          {t('chat.branchIndicator', { current: currentIndex + 1, total: siblings.length })}
        </Text>
        <Button
          type="text"
          size="small"
          icon={<RightOutlined />}
          onClick={handleNext}
          disabled={currentIndex === siblings.length - 1}
          aria-label={t('chat.nextBranch')}
          style={{
            fontSize: 10,
            width: 20,
            height: 20,
            color: token.colorTextSecondary,
          }}
        />
      </Space>
    </div>
  );
}
