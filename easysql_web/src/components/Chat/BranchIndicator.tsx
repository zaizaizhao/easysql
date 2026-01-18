import { Button, Space, Typography } from 'antd';
import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import { useChatStore } from '@/stores';

const { Text } = Typography;

interface BranchIndicatorProps {
  siblings: string[];
  currentIndex: number;
}

export function BranchIndicator({ siblings, currentIndex }: BranchIndicatorProps) {
  const { switchBranch } = useChatStore();

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
          style={{ 
            fontSize: 10, 
            width: 20, 
            height: 20,
            color: 'rgba(0, 0, 0, 0.45)',
          }}
        />
        <Text 
          type="secondary" 
          style={{ fontSize: 11, minWidth: 40, textAlign: 'center' }}
        >
          分支 {currentIndex + 1}/{siblings.length}
        </Text>
        <Button
          type="text"
          size="small"
          icon={<RightOutlined />}
          onClick={handleNext}
          disabled={currentIndex === siblings.length - 1}
          style={{ 
            fontSize: 10, 
            width: 20, 
            height: 20,
            color: 'rgba(0, 0, 0, 0.45)',
          }}
        />
      </Space>
    </div>
  );
}
