import { useState, type KeyboardEvent } from 'react';
import { Input, Button, Space, Tooltip, theme } from 'antd';
import { SendOutlined, LoadingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useChatStore, useAppStore } from '@/stores';

const { TextArea } = Input;

interface ChatInputProps {
  onSend: (message: string) => void;
}

export function ChatInput({ onSend }: ChatInputProps) {
  const { t } = useTranslation();
  const [input, setInput] = useState('');
  const { isLoading } = useChatStore();
  const { currentDatabase } = useAppStore();
  const { token } = theme.useToken();

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setInput('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const getPlaceholder = () => {
    if (!currentDatabase) {
      return t('chat.placeholderNoDb');
    }
    return t('chat.placeholder', { database: currentDatabase.toUpperCase() });
  };

  return (
    <div
      style={{
        padding: 16,
        borderTop: `1px solid ${token.colorBorder}`,
        background: token.colorBgContainer,
      }}
    >
      <Space.Compact style={{ width: '100%' }}>
        <TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={getPlaceholder()}
          disabled={!currentDatabase || isLoading}
          autoSize={{ minRows: 1, maxRows: 4 }}
          style={{ flex: 1 }}
        />
        <Tooltip title={isLoading ? t('chat.processing') : t('chat.sendTooltip')}>
          <Button
            type="primary"
            icon={isLoading ? <LoadingOutlined /> : <SendOutlined />}
            onClick={handleSend}
            disabled={!input.trim() || isLoading || !currentDatabase}
            style={{ height: 'auto' }}
          />
        </Tooltip>
      </Space.Compact>
    </div>
  );
}
