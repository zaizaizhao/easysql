import { Button } from 'antd';
import { BranchesOutlined } from '@ant-design/icons';

interface BranchButtonProps {
  messageId: string;
  onClick: (messageId: string) => void;
  visible?: boolean;
}

export function BranchButton({ messageId, onClick, visible = false }: BranchButtonProps) {
  return (
    <Button
      type="text"
      size="small"
      icon={<BranchesOutlined />}
      onClick={() => onClick(messageId)}
      style={{
        fontSize: 11,
        color: 'var(--primary-color)',
        opacity: visible ? 0.8 : 0,
        transition: 'opacity 0.2s ease',
        padding: '2px 6px',
        height: 'auto',
      }}
    >
      基于此追问
    </Button>
  );
}
