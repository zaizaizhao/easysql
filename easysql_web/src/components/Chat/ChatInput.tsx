import { useState, type KeyboardEvent } from 'react';
import { Input, Button, theme } from 'antd';
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
  const [isFocused, setIsFocused] = useState(false);
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
        padding: '16px 24px 24px',
        background: 'transparent',
      }}
    >
      <div
        style={{
          position: 'relative',
          maxWidth: 900,
          margin: '0 auto',
          background: token.colorBgContainer,
          borderRadius: 12,
          boxShadow: isFocused 
            ? `0 4px 12px ${token.colorFillSecondary}`
            : `0 2px 8px ${token.colorFillQuaternary}`,
          border: `1px solid ${isFocused ? token.colorPrimary : token.colorBorderSecondary}`,
          transition: 'all 0.2s ease',
          padding: '8px 8px 8px 16px',
          display: 'flex',
          alignItems: 'flex-end',
          gap: 8,
        }}
      >
        <TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          placeholder={getPlaceholder()}
          disabled={!currentDatabase || isLoading}
          autoSize={{ minRows: 1, maxRows: 8 }}
          variant="borderless"
          style={{ 
            flex: 1, 
            padding: '8px 0',
            resize: 'none',
            fontSize: 16,
            lineHeight: 1.5,
            maxHeight: 200,
          }}
          autoComplete="off"
        />
        
        <Button
          type="primary"
          shape="circle"
          icon={isLoading ? <LoadingOutlined /> : <SendOutlined />}
          onClick={handleSend}
          disabled={!input.trim() || isLoading || !currentDatabase}
          size="large"
          style={{ 
            flexShrink: 0,
            marginBottom: 2,
            boxShadow: 'none',
            opacity: (!input.trim() || isLoading) ? 0.5 : 1,
          }}
          aria-label={t('chat.send')}
        />
      </div>
      <div 
        style={{ 
          textAlign: 'center', 
          marginTop: 8, 
          fontSize: 12, 
          color: token.colorTextQuaternary 
        }}
      >
        EasySQL generated content may be inaccurate. Please verify important information.
      </div>
    </div>
  );
}
