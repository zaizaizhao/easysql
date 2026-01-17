import { MessageList, ChatInput } from '@/components/Chat';
import { useStreamQuery } from '@/hooks';
import { useChatStore } from '@/stores';

export default function ChatPage() {
  const { sendQuery, continueStream } = useStreamQuery();
  const { sessionId, status } = useChatStore();

  const handleSend = (message: string) => {
    sendQuery(message);
  };

  const handleClarificationAnswer = (answer: string) => {
    if (!sessionId || status !== 'awaiting_clarification') return;
    continueStream(answer);
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'var(--chat-bg)',
        borderRadius: 8,
        overflow: 'hidden',
      }}
    >
      <MessageList onClarificationSelect={handleClarificationAnswer} />
      <ChatInput 
        onSend={handleSend} 
        onClarificationAnswer={handleClarificationAnswer}
      />
    </div>
  );
}
