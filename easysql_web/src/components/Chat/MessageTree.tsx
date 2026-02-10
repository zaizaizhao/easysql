import { useEffect, useRef, useState } from 'react';
import { Empty } from 'antd';
import { useTranslation } from 'react-i18next';
import { MessageItem } from './MessageItem';
import { BranchIndicator } from './BranchIndicator';
import { BranchButton } from './BranchButton';
import { useChatStore } from '@/stores';
import type { ChatMessage } from '@/types';

interface MessageTreeProps {
  onClarificationSelect?: (answer: string) => void;
  onBranchClick?: (messageId: string) => Promise<void> | void;
}

export function MessageTree({ onClarificationSelect, onBranchClick }: MessageTreeProps) {
  const { t } = useTranslation();
  const { getVisibleMessages, messages, messageMap, isLoading } = useChatStore();
  const listRef = useRef<HTMLDivElement>(null);
  const [hoveredMessageId, setHoveredMessageId] = useState<string | null>(null);

  const visibleMessages = getVisibleMessages();
  const lastAssistantMessage = [...visibleMessages]
    .filter((message) => message.role === 'assistant')
    .at(-1);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  if (visibleMessages.length === 0) {
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

  const getSiblings = (message: ChatMessage): string[] => {
    if (!message.parentId) return [message.id];
    const parent = messageMap.get(message.parentId);
    if (!parent || !parent.childIds) return [message.id];
    return parent.childIds;
  };

  const getCurrentIndex = (message: ChatMessage, siblings: string[]): number => {
    return siblings.indexOf(message.id);
  };

  return (
    <div
      ref={listRef}
      style={{
        flex: 1,
        overflow: 'auto',
        padding: '0 16px',
      }}
    >
      {visibleMessages.map((message, index) => {
        const siblings = getSiblings(message);
        const currentIndex = getCurrentIndex(message, siblings);
        const hasBranches = siblings.length > 1;

        const prevUserMessage = message.role === 'assistant' && index > 0 && visibleMessages[index - 1]?.role === 'user'
          ? visibleMessages[index - 1]
          : undefined;

        return (
          <div
            key={message.id}
            onMouseEnter={() => setHoveredMessageId(message.id)}
            onMouseLeave={() => setHoveredMessageId(null)}
            style={{ position: 'relative' }}
          >
            <MessageItem
              message={message}
              onClarificationSelect={onClarificationSelect}
              isLoading={isLoading}
              userQuestion={prevUserMessage?.content}
              isLatestAssistant={message.role === 'assistant' && message.id === lastAssistantMessage?.id}
            />
            
            {hasBranches && (
              <BranchIndicator
                siblings={siblings}
                currentIndex={currentIndex}
              />
            )}
            
            {message.role === 'assistant' && !message.isStreaming && (
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'flex-start',
                  paddingLeft: 48,
                  marginTop: -8,
                  marginBottom: 8,
                }}
              >
                <BranchButton
                  messageId={message.id}
                  onClick={(id) => onBranchClick?.(id)}
                  visible={hoveredMessageId === message.id}
                  disabled={isLoading}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
