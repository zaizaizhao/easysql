import { useEffect, useRef, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
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
  const navigate = useNavigate();
  const location = useLocation();
  
  const { data, isLoading, refetch } = useSessions();
  const deleteSessionMutation = useDeleteSession();
  
  const { 
    sessionId: currentSessionId, 
    sessions: storeSessions,
    setSessions, 
    switchSession,
    removeSession,
    messages: currentMessages,
    sessionCache,
  } = useChatStore();

  const prevSessionIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (data?.sessions) {
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
    const isOnChatPage = location.pathname.startsWith('/chat');
    
    if (sessionId === currentSessionId && isOnChatPage) return;
    
    if (sessionId === currentSessionId && !isOnChatPage) {
      navigate(`/chat/${sessionId}`);
      return;
    }
    
    try {
      const detail = await getSessionDetail(sessionId);
      
      const messages: ChatMessage[] = [];
      let currentUserMsg: ChatMessage | null = null;
      let currentAssistantData: {
        clarificationQuestions?: string[];
        userAnswer?: string;
        sql?: string;
        validationPassed?: boolean;
        content?: string;
        timestamp?: Date;
      } = {};
      let msgIndex = 0;
      
      const flushAssistant = () => {
        if (currentUserMsg && (currentAssistantData.sql || currentAssistantData.clarificationQuestions || currentAssistantData.content)) {
          messages.push(currentUserMsg);
          messages.push({
            id: `${sessionId}_msg_${msgIndex++}`,
            role: 'assistant',
            content: currentAssistantData.content || '',
            timestamp: currentAssistantData.timestamp || new Date(),
            sql: currentAssistantData.sql,
            validationPassed: currentAssistantData.validationPassed,
            clarificationQuestions: currentAssistantData.clarificationQuestions,
            userAnswer: currentAssistantData.userAnswer,
          });
          currentUserMsg = null;
          currentAssistantData = {};
        }
      };
      
      for (const m of detail.messages) {
        if (m.role === 'user') {
          if (m.user_answer) {
            currentAssistantData.userAnswer = m.user_answer;
          } else {
            flushAssistant();
            currentUserMsg = {
              id: `${sessionId}_msg_${msgIndex++}`,
              role: 'user',
              content: m.content,
              timestamp: new Date(m.timestamp),
            };
          }
        } else if (m.role === 'assistant') {
          if (!currentAssistantData.timestamp) {
            currentAssistantData.timestamp = new Date(m.timestamp);
          }
          if (m.clarification_questions?.length) {
            currentAssistantData.clarificationQuestions = m.clarification_questions;
          }
          if (m.sql) {
            currentAssistantData.sql = m.sql;
            currentAssistantData.validationPassed = m.validation_passed;
          }
          if (m.content && !currentAssistantData.content) {
            currentAssistantData.content = m.content;
          }
        }
      }
      flushAssistant();
      
      switchSession(sessionId, messages);
      
      if (!location.pathname.startsWith('/chat')) {
        navigate(`/chat/${sessionId}`);
      }
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
                        const isCurrentActive = session.session_id === currentSessionId;
                        let messagesForTitle: typeof currentMessages = [];
                        
                        if (isCurrentActive) {
                          messagesForTitle = currentMessages;
                        } else {
                          const cached = sessionCache.get(session.session_id);
                          if (cached) {
                            messagesForTitle = cached.messages;
                          }
                        }
                        
                        const userMsg = messagesForTitle.find(m => m.role === 'user');
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
