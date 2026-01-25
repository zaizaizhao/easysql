import { useEffect, useRef, useMemo } from 'react';
import { Typography, Button, Popconfirm, Spin, theme, message } from 'antd';
import { DeleteOutlined, MessageOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '@/stores';
import type { ChatMessage, SessionInfo } from '@/types';
import { useSessions, useDeleteSession } from '@/hooks';
import { getSessionDetail } from '@/api';
import axios from 'axios';

const { Text } = Typography;

interface SessionListProps {
  collapsed?: boolean;
}

export function SessionList({ collapsed }: SessionListProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  
  const { data, isLoading, refetch } = useSessions();
  const deleteSessionMutation = useDeleteSession();
  
  const { 
    sessionId: currentSessionId, 
    sessions: storeSessions,
    setSessions, 
    switchSession,
    removeSession,
    messages: currentMessages,
  } = useChatStore();

  const prevSessionIdRef = useRef<string | null>(null);
  const initialLoadDoneRef = useRef(false);

  useEffect(() => {
    if (data?.sessions && !initialLoadDoneRef.current) {
      initialLoadDoneRef.current = true;
      setSessions(data.sessions);
    }
  }, [data?.sessions, setSessions]);

  useEffect(() => {
    if (prevSessionIdRef.current && !currentSessionId) {
      refetch();
    }
    prevSessionIdRef.current = currentSessionId;
  }, [currentSessionId, refetch]);

  const handleSessionClick = async (sessionId: string) => {
    if (sessionId === currentSessionId) return;
    
    try {
      const detail = await getSessionDetail(sessionId);
      
      // 合并消息：用户问题(1条) + 助手完整回复(1条，含澄清+回答+SQL+表格)
      const mergedMessages: ChatMessage[] = [];
      
      let firstUserQuestion: ChatMessage | null = null;
      let assistantData: {
        clarificationQuestions?: string[];
        userAnswer?: string;
        sql?: string;
        validationPassed?: boolean;
        content?: string;
        timestamp?: Date;
      } = {};
      
      for (const m of detail.messages) {
        if (m.role === 'user') {
          if (!firstUserQuestion && !m.user_answer) {
            firstUserQuestion = {
              id: `${sessionId}_user`,
              role: 'user',
              content: m.content,
              timestamp: new Date(m.timestamp),
            };
          }
          if (m.user_answer) {
            assistantData.userAnswer = m.user_answer;
          }
        } else if (m.role === 'assistant') {
          if (!assistantData.timestamp) {
            assistantData.timestamp = new Date(m.timestamp);
          }
          if (m.clarification_questions && m.clarification_questions.length > 0) {
            assistantData.clarificationQuestions = m.clarification_questions;
          }
          if (m.sql) {
            assistantData.sql = m.sql;
            assistantData.validationPassed = m.validation_passed;
          }
          if (m.content && !assistantData.content) {
            assistantData.content = m.content;
          }
        }
      }
      
      if (firstUserQuestion) {
        mergedMessages.push(firstUserQuestion);
        mergedMessages.push({
          id: `${sessionId}_assistant`,
          role: 'assistant',
          content: assistantData.content || '',
          timestamp: assistantData.timestamp || new Date(),
          sql: assistantData.sql || detail.generated_sql || undefined,
          validationPassed: assistantData.validationPassed ?? detail.validation_passed ?? undefined,
          clarificationQuestions: assistantData.clarificationQuestions,
          userAnswer: assistantData.userAnswer,
        });
      }
      
      const messages = mergedMessages.length > 0 ? mergedMessages : detail.messages.map((m, idx) => ({
        id: `${sessionId}_msg_${idx}`,
        role: m.role as 'user' | 'assistant',
        content: m.content,
        timestamp: new Date(m.timestamp),
        sql: m.sql || undefined,
        validationPassed: m.validation_passed ?? undefined,
        clarificationQuestions: m.clarification_questions || undefined,
        userAnswer: m.user_answer || undefined,
      }));
      
      switchSession(sessionId, messages);
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        removeSession(sessionId);
        message.warning(t('session.loadError', 'Session not found'));
      } else {
        console.error('Failed to load session:', error);
        message.error(t('session.loadError', 'Failed to load session'));
      }
    }
  };

  const handleDeleteSession = async (sessionId: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    try {
      await deleteSessionMutation.mutateAsync(sessionId);
      removeSession(sessionId);
      refetch();
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  };

  const getSessionTitle = (sessionId: string, index: number): string => {
    const session = storeSessions.find(s => s.session_id === sessionId);
    if (!session) return `${t('nav.chat')} ${index + 1}`;
    
    const cached = useChatStore.getState().sessionCache.get(sessionId);
    if (cached?.title) return cached.title;
    
    // Default title from session ID or date if no messages
    return `Session ${sessionId.slice(0, 6)}`;
  };

  const groupedSessions = useMemo(() => {
    const groups: Record<string, (SessionInfo | { session_id: string; isCurrentUnsaved: boolean })[]> = {
      today: [],
      yesterday: [],
      previous7Days: [],
      older: [],
    };

    const currentInStore = storeSessions.find(s => s.session_id === currentSessionId);
    let allSessions = [...storeSessions];
    
    if (currentSessionId && !currentInStore) {
        // Add unsaved current session to the top
        allSessions = [{ session_id: currentSessionId, isCurrentUnsaved: true, updated_at: new Date().toISOString() } as any, ...allSessions];
    }

    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const weekAgo = new Date(today);
    weekAgo.setDate(weekAgo.getDate() - 7);

    allSessions.forEach(session => {
        const date = new Date(session.updated_at);
        const sessionDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());

        if (sessionDate.getTime() === today.getTime()) {
            groups.today.push(session);
        } else if (sessionDate.getTime() === yesterday.getTime()) {
            groups.yesterday.push(session);
        } else if (sessionDate > weekAgo) {
            groups.previous7Days.push(session);
        } else {
            groups.older.push(session);
        }
    });

    return groups;
  }, [storeSessions, currentSessionId]);

  if (collapsed) {
    return null;
  }

  if (isLoading && storeSessions.length === 0) {
    return (
      <div style={{ padding: 16, textAlign: 'center' }}>
        <Spin size="small" />
      </div>
    );
  }

  if (storeSessions.length === 0 && !currentSessionId) {
    return (
      <div style={{ padding: '8px 12px' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {t('session.empty')}
        </Text>
      </div>
    );
  }

  const renderSessionGroup = (title: string, sessions: typeof groupedSessions['today']) => {
      if (sessions.length === 0) return null;
      return (
          <div key={title} style={{ marginBottom: 12 }}>
              <Text 
                type="secondary" 
                style={{ 
                  fontSize: 11, 
                  padding: '0 12px', 
                  display: 'block',
                  marginBottom: 4,
                  textTransform: 'uppercase',
                  letterSpacing: 0.5,
                  fontWeight: 600,
                }}
              >
                {t(`session.group.${title}`, title)}
              </Text>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {sessions.map((session, index) => {
                      const isActive = session.session_id === currentSessionId;
                      const isUnsaved = 'isCurrentUnsaved' in session;
                      
                      let sessionTitle: string;
                      if (isUnsaved) {
                        const userMsg = currentMessages.find(m => m.role === 'user');
                        sessionTitle = userMsg?.content.slice(0, 30) || t('nav.newChat');
                      } else {
                        sessionTitle = getSessionTitle(session.session_id, index);
                      }

                      return (
                        <div
                          key={session.session_id}
                          role="button"
                          tabIndex={0}
                          onClick={() => handleSessionClick(session.session_id)}
                          style={{
                            padding: '8px 12px',
                            cursor: 'pointer',
                            background: isActive ? token.colorPrimaryBg : 'transparent',
                            borderRadius: 6,
                            margin: '0 4px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            transition: 'all 0.2s',
                            width: 'calc(100% - 8px)',
                            textAlign: 'left',
                            position: 'relative',
                          }}
                          className="session-item"
                        >
                          <div style={{ 
                            display: 'flex', 
                            alignItems: 'center', 
                            gap: 8,
                            overflow: 'hidden',
                            flex: 1,
                          }}>
                            <MessageOutlined style={{ fontSize: 14, opacity: 0.6, flexShrink: 0 }} />
                            <Text 
                              ellipsis 
                              style={{ 
                                fontSize: 13,
                                fontWeight: isActive ? 500 : 400,
                                color: isActive ? token.colorPrimary : token.colorText,
                                lineHeight: 1.5,
                              }}
                            >
                              {sessionTitle}
                            </Text>
                          </div>
                          
                          {!isUnsaved && (
                            <div 
                              className="session-actions"
                              style={{ 
                                opacity: isActive ? 1 : 0,
                                transition: 'opacity 0.2s',
                              }}
                            >
                              <Popconfirm
                                title={t('session.deleteConfirm')}
                                onConfirm={(e) => handleDeleteSession(session.session_id, e as React.MouseEvent)}
                                onCancel={(e) => e?.stopPropagation()}
                                okText={t('common.confirm')}
                                cancelText={t('common.cancel')}
                              >
                                <Button
                                  type="text"
                                  size="small"
                                  icon={<DeleteOutlined />}
                                  onClick={(e) => e.stopPropagation()}
                                  style={{ 
                                    width: 24, 
                                    height: 24, 
                                    fontSize: 12, 
                                    color: token.colorTextSecondary,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                  }}
                                />
                              </Popconfirm>
                            </div>
                          )}
                        </div>
                      );
                  })}
              </div>
          </div>
      );
  };

  return (
    <div style={{ marginTop: 8 }}>
        {renderSessionGroup('today', groupedSessions.today)}
        {renderSessionGroup('yesterday', groupedSessions.yesterday)}
        {renderSessionGroup('previous7Days', groupedSessions.previous7Days)}
        {renderSessionGroup('older', groupedSessions.older)}
        
      <style>
        {`
          .session-item:hover {
            background: ${token.colorFillQuaternary} !important;
          }
          .session-item:hover .session-actions {
            opacity: 1 !important;
          }
        `}
      </style>
    </div>
  );
}
