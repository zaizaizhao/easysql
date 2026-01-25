import { useState } from 'react';
import { Modal, Input, theme } from 'antd';
import { useTranslation } from 'react-i18next';
import { MessageTree, ChatInput } from '@/components/Chat';
import { useStreamQuery } from '@/hooks';
import { useChatStore } from '@/stores';

export default function ChatPage() {
  const { t } = useTranslation();
  const { sendQuery, continueStream, sendFollowUp, createBranch } = useStreamQuery();
  const { sessionId } = useChatStore();
  const { token } = theme.useToken();
  
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
    if (!sessionId) return;
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
        background: token.colorBgLayout,
        borderRadius: 8,
        overflow: 'hidden',
      }}
    >
      <MessageTree 
        onClarificationSelect={handleClarificationAnswer}
        onBranchClick={handleBranchClick}
      />
      <ChatInput onSend={handleSend} />
      
      <Modal
        title={t('chat.modalTitle')}
        open={branchModalVisible}
        onOk={handleBranchSubmit}
        onCancel={handleBranchCancel}
        okText={t('chat.modalOk')}
        cancelText={t('chat.modalCancel')}
        okButtonProps={{ disabled: !branchQuestion.trim() }}
      >
        <Input.TextArea
          value={branchQuestion}
          onChange={(e) => setBranchQuestion(e.target.value)}
          placeholder={t('chat.modalPlaceholder') + '…'}
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
