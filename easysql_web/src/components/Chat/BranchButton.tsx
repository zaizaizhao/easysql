import { Button, theme } from 'antd';
import { BranchesOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

interface BranchButtonProps {
  messageId: string;
  onClick: (messageId: string) => void;
  visible?: boolean;
}

export function BranchButton({ messageId, onClick, visible = false }: BranchButtonProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  return (
    <Button
      type="text"
      size="small"
      icon={<BranchesOutlined />}
      onClick={() => onClick(messageId)}
      aria-label={t('chat.branchFollowUp')}
      style={{
        fontSize: 11,
        color: token.colorPrimary,
        opacity: visible ? 0.8 : 0,
        transition: 'opacity 0.2s ease',
        padding: '2px 6px',
        height: 'auto',
      }}
    >
      {t('chat.branchFollowUp')}
    </Button>
  );
}
