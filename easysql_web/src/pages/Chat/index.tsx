import { useEffect, useState } from 'react';
import { Modal, Input, theme, message as antMessage } from 'antd';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { MessageTree, ChatInput, WelcomeScreen } from '@/components/Chat';
import { getSessionDetail } from '@/api';
import { useStreamQuery } from '@/hooks';
import { useChatStore } from '@/stores';
import type { ChatMessage, SessionDetail } from '@/types';
import axios from 'axios';

export default function ChatPage() {
  const { t } = useTranslation();
  const { sendQuery, continueStream, sendFollowUp, createBranch } = useStreamQuery();
  const { sessionId: routeSessionId } = useParams<{ sessionId?: string }>();
  const {
    sessionId,
    sessionCache,
    status,
    switchSession,
    removeSession,
  } = useChatStore();
  const { token } = theme.useToken();
  
  const [branchModalVisible, setBranchModalVisible] = useState(false);
  const [branchFromMessageId, setBranchFromMessageId] = useState<string | null>(null);
  const [branchQuestion, setBranchQuestion] = useState('');

  useEffect(() => {
    if (!routeSessionId) return;
    if (routeSessionId === sessionId && status !== 'pending') return;

    const cached = sessionCache.get(routeSessionId);
    if (cached) {
      switchSession(routeSessionId);
      return;
    }

    let cancelled = false;

    const buildMessages = (detail: SessionDetail): ChatMessage[] => {
      const nextMessages: ChatMessage[] = [];
      let msgIndex = 0;

      for (const turn of detail.turns || []) {
        nextMessages.push({
          id: `${detail.session_id}_msg_${msgIndex++}`,
          role: 'user',
          content: turn.question,
          timestamp: new Date(turn.created_at),
          isHistorical: true,
        });

        const assistantMsg: ChatMessage = {
          id: `${detail.session_id}_msg_${msgIndex++}`,
          role: 'assistant',
          content: '',
          timestamp: new Date(turn.created_at),
          sql: turn.final_sql,
          validationPassed: turn.validation_passed,
          turnId: turn.turn_id,
          chartPlan: turn.chart_plan,
          chartReasoning: turn.chart_reasoning,
          isHistorical: true,
        };

        if (turn.clarifications && turn.clarifications.length > 0) {
          const lastClarification = turn.clarifications[turn.clarifications.length - 1];
          assistantMsg.clarificationQuestions = lastClarification.questions;
          assistantMsg.userAnswer = lastClarification.answer;
        }

        if (turn.error) {
          assistantMsg.content = turn.error;
        }

        nextMessages.push(assistantMsg);
      }

      return nextMessages;
    };

    const loadSession = async () => {
      try {
        const detail = await getSessionDetail(routeSessionId);
        if (cancelled) return;
        const loadedMessages = buildMessages(detail);
        switchSession(routeSessionId, loadedMessages);
      } catch (error) {
        if (cancelled) return;
        if (axios.isAxiosError(error) && error.response?.status === 404) {
          removeSession(routeSessionId);
          antMessage.warning(t('session.loadError', 'Session not found'));
        } else {
          console.error('Failed to load session:', error);
          antMessage.error(t('session.loadError', 'Failed to load session'));
        }
      }
    };

    loadSession();

    return () => {
      cancelled = true;
    };
  }, [routeSessionId, sessionId, status, sessionCache, switchSession, removeSession, t]);

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
      {!sessionId ? (
        <WelcomeScreen onSend={handleSend} />
      ) : (
        <>
          <MessageTree 
            onClarificationSelect={handleClarificationAnswer}
            onBranchClick={handleBranchClick}
          />
          <ChatInput onSend={handleSend} />
        </>
      )}
      
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
