import { useEffect, useRef } from 'react';
import { Empty } from 'antd';
import { useTranslation } from 'react-i18next';
import { MessageItem } from './MessageItem';
import { useChatStore } from '@/stores';

interface MessageListProps {
  onClarificationSelect?: (answer: string) => void;
}

export function MessageList({ onClarificationSelect }: MessageListProps) {
  const { t } = useTranslation();
  const { messages } = useChatStore();
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
        }}
      >
        <Empty
          description={t('chat.startNewConversation')}
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </div>
    );
  }

  const lastAssistantIndex = [...messages]
    .map((msg, idx) => ({ msg, idx }))
    .filter(({ msg }) => msg.role === 'assistant')
    .map(({ idx }) => idx)
    .at(-1);

  return (
    <div
      ref={listRef}
      style={{
        flex: 1,
        overflow: 'auto',
        padding: '0 16px',
      }}
    >
      {messages.map((message, index) => {
        const prevUserMessage = message.role === 'assistant' && index > 0 && messages[index - 1]?.role === 'user'
          ? messages[index - 1]
          : undefined;
        return (
          <MessageItem
            key={message.id}
            message={message}
            onClarificationSelect={onClarificationSelect}
            userQuestion={prevUserMessage?.content}
            isLatestAssistant={message.role === 'assistant' && index === lastAssistantIndex}
          />
        );
      })}
    </div>
  );
}
