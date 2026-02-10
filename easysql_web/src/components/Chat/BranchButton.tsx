import { Button, Popconfirm, theme } from 'antd';
import { BranchesOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

interface BranchButtonProps {
  messageId: string;
  onClick: (messageId: string) => Promise<void> | void;
  visible?: boolean;
  disabled?: boolean;
}

export function BranchButton({
  messageId,
  onClick,
  visible = false,
  disabled = false,
}: BranchButtonProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();

  return (
    <Popconfirm
      title={t('chat.forkConfirmTitle')}
      description={t('chat.forkConfirmDescription')}
      okText={t('chat.forkConfirmOk')}
      cancelText={t('chat.forkConfirmCancel')}
      onConfirm={() => onClick(messageId)}
      disabled={disabled}
      placement="topLeft"
    >
      <Button
        type="text"
        size="small"
        icon={<BranchesOutlined />}
        aria-label={t('chat.branchFollowUp')}
        disabled={disabled}
        onClick={(event) => event.stopPropagation()}
        style={{
          fontSize: 11,
          color: token.colorPrimary,
          opacity: visible ? 0.8 : 0,
          transition: 'opacity 0.2s ease',
          padding: '2px 6px',
          height: 'auto',
          pointerEvents: visible ? 'auto' : 'none',
        }}
      >
        {t('chat.branchFollowUp')}
      </Button>
    </Popconfirm>
  );
}
