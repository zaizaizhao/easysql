import { useEffect } from 'react';
import { theme, message as antMessage } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
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
  const navigate = useNavigate();
  const { sessionId: routeSessionId } = useParams<{ sessionId?: string }>();
  const {
    sessionId,
    switchSession,
    removeSession,
  } = useChatStore();
  const { token } = theme.useToken();

  useEffect(() => {
    if (!routeSessionId) return;

    const {
      sessionId: currentSessionId,
      status: currentStatus,
      sessionCache: currentSessionCache,
    } = useChatStore.getState();

    if (routeSessionId === currentSessionId && currentStatus !== 'pending') return;

    const cached = currentSessionCache.get(routeSessionId);
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
          serverId: turn.assistant_message_id,
          isFewShot: turn.assistant_is_few_shot,
          retrievalSummary: {
            tablesCount: turn.tables_used?.length || 0,
            tables: turn.tables_used || [],
          },
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
  }, [routeSessionId, switchSession, removeSession, t]);

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

  const handleBranchClick = async (messageId: string) => {
    const noticeKey = `fork-${messageId}`;
    antMessage.open({
      key: noticeKey,
      type: 'loading',
      content: t('chat.forkCreating'),
      duration: 0,
    });

    const newSessionId = await createBranch(messageId);
    if (newSessionId) {
      antMessage.open({
        key: noticeKey,
        type: 'success',
        content: t('chat.forkCreated'),
        duration: 1.5,
      });
      navigate(`/chat/${newSessionId}`);
      return;
    }

    antMessage.open({
      key: noticeKey,
      type: 'error',
      content: t('chat.forkFailed'),
      duration: 2,
    });
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
    </div>
  );
}
