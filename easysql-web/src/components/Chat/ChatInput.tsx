import { useState, type KeyboardEvent } from 'react';
import { Input, Button, Space, Tooltip, Tag } from 'antd';
import { SendOutlined, LoadingOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import { useChatStore, useAppStore } from '@/stores';

const { TextArea } = Input;

interface ChatInputProps {
  onSend: (message: string) => void;
  onClarificationAnswer?: (answer: string) => void;
}

export function ChatInput({ onSend, onClarificationAnswer }: ChatInputProps) {
  const [input, setInput] = useState('');
  const { isLoading, status } = useChatStore();
  const { currentDatabase } = useAppStore();

  const isAwaitingClarification = status === 'awaiting_clarification';

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    
    if (isAwaitingClarification && onClarificationAnswer) {
      onClarificationAnswer(trimmed);
    } else {
      onSend(trimmed);
    }
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
      return '请先选择数据库...';
    }
    if (isAwaitingClarification) {
      return '请输入您的回答... (Enter 发送)';
    }
    return `向 ${currentDatabase.toUpperCase()} 数据库提问... (Enter 发送, Shift+Enter 换行)`;
  };

  return (
    <div
      style={{
        padding: 16,
        borderTop: '1px solid var(--border-color)',
        background: 'var(--input-area-bg)',
      }}
    >
      {isAwaitingClarification && (
        <div style={{ marginBottom: 8 }}>
          <Tag icon={<QuestionCircleOutlined />} color="warning">
            等待您的回答
          </Tag>
        </div>
      )}
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
        <Tooltip title={isLoading ? '处理中...' : '发送 (Enter)'}>
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
