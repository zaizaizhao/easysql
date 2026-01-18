import { useState } from 'react';
import { Modal, Input } from 'antd';
import { MessageTree, ChatInput } from '@/components/Chat';
import { useStreamQuery } from '@/hooks';
import { useChatStore } from '@/stores';

export default function ChatPage() {
  const { sendQuery, continueStream, sendFollowUp, createBranch } = useStreamQuery();
  const { sessionId, status } = useChatStore();
  
  const [branchModalVisible, setBranchModalVisible] = useState(false);
  const [branchFromMessageId, setBranchFromMessageId] = useState<string | null>(null);
  const [branchQuestion, setBranchQuestion] = useState('');

  const handleSend = (message: string) => {
    if (sessionId) {
      sendFollowUp(message);
    } else {
      sendQuery(message);
    }
  };

  const handleClarificationAnswer = (answer: string) => {
    if (!sessionId || status !== 'awaiting_clarification') return;
    continueStream(answer);
  };

  const handleBranchClick = (messageId: string) => {
    setBranchFromMessageId(messageId);
    setBranchModalVisible(true);
  };

  const handleBranchSubmit = () => {
    if (branchFromMessageId && branchQuestion.trim()) {
      createBranch(branchQuestion.trim(), branchFromMessageId);
      setBranchModalVisible(false);
      setBranchQuestion('');
      setBranchFromMessageId(null);
    }
  };

  const handleBranchCancel = () => {
    setBranchModalVisible(false);
    setBranchQuestion('');
    setBranchFromMessageId(null);
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
      <MessageTree 
        onClarificationSelect={handleClarificationAnswer}
        onBranchClick={handleBranchClick}
      />
      <ChatInput 
        onSend={handleSend} 
        onClarificationAnswer={handleClarificationAnswer}
      />
      
      <Modal
        title="基于此消息追问"
        open={branchModalVisible}
        onOk={handleBranchSubmit}
        onCancel={handleBranchCancel}
        okText="发送"
        cancelText="取消"
        okButtonProps={{ disabled: !branchQuestion.trim() }}
      >
        <Input.TextArea
          value={branchQuestion}
          onChange={(e) => setBranchQuestion(e.target.value)}
          placeholder="输入您的追问..."
          rows={4}
          autoFocus
          onPressEnter={(e) => {
            if (e.ctrlKey || e.metaKey) {
              handleBranchSubmit();
            }
          }}
        />
      </Modal>
    </div>
  );
}
