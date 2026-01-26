import { useEffect, useRef } from 'react';
import { Empty } from 'antd';
import { MessageItem } from './MessageItem';
import { useChatStore } from '@/stores';

interface MessageListProps {
  onClarificationSelect?: (answer: string) => void;
}

export function MessageList({ onClarificationSelect }: MessageListProps) {
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
          description="开始一个新的对话"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </div>
    );
  }

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
          />
        );
      })}
    </div>
  );
}
