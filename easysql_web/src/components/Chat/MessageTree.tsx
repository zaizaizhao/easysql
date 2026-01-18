import { useEffect, useRef, useState } from 'react';
import { Empty } from 'antd';
import { MessageItem } from './MessageItem';
import { BranchIndicator } from './BranchIndicator';
import { BranchButton } from './BranchButton';
import { useChatStore, type ChatMessage } from '@/stores';

interface MessageTreeProps {
  onClarificationSelect?: (answer: string) => void;
  onBranchClick?: (messageId: string) => void;
}

export function MessageTree({ onClarificationSelect, onBranchClick }: MessageTreeProps) {
  const { getVisibleMessages, messages, messageMap } = useChatStore();
  const listRef = useRef<HTMLDivElement>(null);
  const [hoveredMessageId, setHoveredMessageId] = useState<string | null>(null);

  const visibleMessages = getVisibleMessages();

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
          description="开始一个新的对话"
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
      {visibleMessages.map((message) => {
        const siblings = getSiblings(message);
        const currentIndex = getCurrentIndex(message, siblings);
        const hasBranches = siblings.length > 1;

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
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
