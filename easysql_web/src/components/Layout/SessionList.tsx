import { useEffect, useRef } from 'react';
import { Typography, Button, Popconfirm, Spin, theme, message } from 'antd';
import { DeleteOutlined, MessageOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '@/stores';
import { useSessions, useDeleteSession } from '@/hooks';
import { getSessionDetail } from '@/api';
import type { ChatMessage } from '@/stores/chatStore';
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
      const messages: ChatMessage[] = detail.messages.map((m, idx) => ({
        id: `${sessionId}_msg_${idx}`,
        role: m.role as 'user' | 'assistant',
        content: m.content,
        timestamp: new Date(m.timestamp),
        sql: detail.generated_sql || undefined,
        validationPassed: detail.validation_passed ?? undefined,
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
    
    const date = new Date(session.updated_at);
    return date.toLocaleDateString();
  };

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
          {t('session.empty', '暂无会话')}
        </Text>
      </div>
    );
  }

  const currentInStore = storeSessions.find(s => s.session_id === currentSessionId);
  const displaySessions = currentSessionId && !currentInStore
    ? [{ session_id: currentSessionId, isCurrentUnsaved: true } as const, ...storeSessions]
    : storeSessions;

  return (
    <div style={{ marginTop: 8 }}>
      <Text 
        type="secondary" 
        style={{ 
          fontSize: 11, 
          padding: '0 12px', 
          display: 'block',
          marginBottom: 4,
          textTransform: 'uppercase',
          letterSpacing: 0.5,
        }}
      >
        {t('session.history', '历史会话')}
      </Text>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {displaySessions.map((session, index) => {
          const isActive = session.session_id === currentSessionId;
          const isUnsaved = 'isCurrentUnsaved' in session;
          
          let title: string;
          if (isUnsaved) {
            const userMsg = currentMessages.find(m => m.role === 'user');
            title = userMsg?.content.slice(0, 30) || t('nav.newChat');
          } else {
            title = getSessionTitle(session.session_id, index);
          }
          
          return (
            <div
              key={session.session_id}
              onClick={() => handleSessionClick(session.session_id)}
              style={{
                padding: '6px 12px',
                cursor: 'pointer',
                background: isActive ? token.colorPrimaryBg : 'transparent',
                borderRadius: 6,
                margin: '0 4px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                transition: 'background 0.2s',
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
                <MessageOutlined style={{ fontSize: 12, opacity: 0.6, flexShrink: 0 }} />
                <Text 
                  ellipsis 
                  style={{ 
                    fontSize: 13,
                    fontWeight: isActive ? 500 : 400,
                    color: isActive ? token.colorPrimary : token.colorText,
                  }}
                >
                  {title}
                </Text>
              </div>
              
              {!isUnsaved && (
                <div 
                  className="session-actions"
                  style={{ opacity: isActive ? 1 : 0 }}
                >
                  <Popconfirm
                    title={t('session.deleteConfirm', '确定删除此会话？')}
                    onConfirm={(e) => handleDeleteSession(session.session_id, e as React.MouseEvent)}
                    onCancel={(e) => e?.stopPropagation()}
                    okText={t('common.confirm', '确定')}
                    cancelText={t('common.cancel', '取消')}
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={<DeleteOutlined />}
                      onClick={(e) => e.stopPropagation()}
                      style={{ 
                        width: 20, 
                        height: 20, 
                        fontSize: 12, 
                        color: token.colorTextSecondary 
                      }}
                    />
                  </Popconfirm>
                </div>
              )}
            </div>
          );
        })}
      </div>
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
