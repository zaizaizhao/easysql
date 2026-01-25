import type { ChatMessage, StreamEvent, QueryStatus, SessionCache, AgentStep } from '@/types';

export interface StreamHandlerResult {
  messages?: ChatMessage[];
  messageMap?: Map<string, ChatMessage>;
  sessionCache?: Map<string, SessionCache>;
  isLoading?: boolean;
  status?: QueryStatus;
  error?: string | null;
  sessionId?: string;
}

const updateSessionState = (
  currentMessages: ChatMessage[],
  currentMap: Map<string, ChatMessage>,
  updates: Partial<ChatMessage>,
): { messages: ChatMessage[]; messageMap: Map<string, ChatMessage> } | null => {
  const streamingMessage = currentMessages.find(
    (m) => m.role === 'assistant' && m.isStreaming
  );

  if (!streamingMessage) return null;

  const newMessages = currentMessages.map((msg) =>
    msg.id === streamingMessage.id ? { ...msg, ...updates } : msg
  );

  const newMap = new Map(currentMap);
  if (newMap.has(streamingMessage.id)) {
    newMap.set(streamingMessage.id, {
      ...newMap.get(streamingMessage.id)!,
      ...updates,
    });
  }

  return { messages: newMessages, messageMap: newMap };
};

export const processStreamEvent = (
  event: StreamEvent,
  currentState: {
    sessionId: string | null;
    messages: ChatMessage[];
    messageMap: Map<string, ChatMessage>;
    sessionCache: Map<string, SessionCache>;
    status: QueryStatus;
  }
): StreamHandlerResult => {
  const { sessionId, messages, messageMap, sessionCache } = currentState;
  const eventSessionId = event.data?.session_id;
  
  // Logic Fix: If we are in "new chat" mode (sessionId is null),
  // any valid event with session_id becomes the active session.
  const targetSessionId = eventSessionId || sessionId;

  if (!targetSessionId) return {};

  const isActive = targetSessionId === sessionId || (sessionId === null && !!eventSessionId);

  switch (event.event) {
    case 'start': {
      if (isActive) {
        return {
          sessionId: targetSessionId,
          isLoading: true,
          status: 'processing',
        };
      } else {
        const cached = sessionCache.get(targetSessionId);
        if (cached) {
          const newCache = new Map(sessionCache);
          newCache.set(targetSessionId, { ...cached, status: 'processing' });
          return { sessionCache: newCache };
        }
      }
      break;
    }

    case 'state_update': {
      const updates: Partial<ChatMessage> = {};

      if (event.data.node) {
        let currentTrace: any[] = [];

        if (isActive) {
          const msg = messages.find((m) => m.role === 'assistant' && m.isStreaming);
          currentTrace = msg?.trace || [];
        } else {
          const cached = sessionCache.get(targetSessionId);
          const msg = cached?.messages.find(
            (m) => m.role === 'assistant' && m.isStreaming
          );
          currentTrace = msg?.trace || [];
        }

        const lastStep = currentTrace[currentTrace.length - 1];
        let updatedTrace = [...currentTrace];

        if (lastStep?.node === event.data.node) {
          updatedTrace[updatedTrace.length - 1] = {
            ...lastStep,
            data: { ...lastStep.data, ...event.data },
          };
        } else {
          updatedTrace.push({
            node: event.data.node,
            data: event.data,
            timestamp: Date.now(),
          });
        }
        updates.trace = updatedTrace;
      }

      if (event.data.generated_sql) updates.sql = event.data.generated_sql;
      if (event.data.clarification_questions)
        updates.clarificationQuestions = event.data.clarification_questions;
      if (event.data.retrieval_summary) {
        updates.retrievalSummary = {
          tablesCount: event.data.retrieval_summary.tables_count,
          tables: event.data.retrieval_summary.tables,
        };
      }

      if (Object.keys(updates).length > 0) {
        if (isActive) {
          const result = updateSessionState(messages, messageMap, updates);
          if (result) {
            return {
              messages: result.messages,
              messageMap: result.messageMap,
            };
          }
        } else {
          const cached = sessionCache.get(targetSessionId);
          if (cached) {
            const result = updateSessionState(
              cached.messages,
              cached.messageMap,
              updates
            );
            if (result) {
              const newCache = new Map(sessionCache);
              newCache.set(targetSessionId, {
                ...cached,
                messages: result.messages,
                messageMap: result.messageMap,
              });
              return { sessionCache: newCache };
            }
          }
        }
      }
      break;
    }

    case 'agent_progress': {
      const eventType = event.data.type;
      
      if (eventType === 'token') {
        const tokenContent = event.data.content || '';
        
        if (isActive) {
          const msg = messages.find((m) => m.role === 'assistant' && m.isStreaming);
          if (msg) {
            const currentThinking = msg.thinkingContent || '';
            const result = updateSessionState(messages, messageMap, { 
              thinkingContent: currentThinking + tokenContent 
            });
            if (result) {
              return { messages: result.messages, messageMap: result.messageMap };
            }
          }
        } else {
          const cached = sessionCache.get(targetSessionId);
          if (cached) {
            const msg = cached.messages.find((m) => m.role === 'assistant' && m.isStreaming);
            if (msg) {
              const currentThinking = msg.thinkingContent || '';
              const result = updateSessionState(cached.messages, cached.messageMap, { 
                thinkingContent: currentThinking + tokenContent 
              });
              if (result) {
                const newCache = new Map(sessionCache);
                newCache.set(targetSessionId, {
                  ...cached,
                  messages: result.messages,
                  messageMap: result.messageMap,
                });
                return { sessionCache: newCache };
              }
            }
          }
        }
        break;
      }
      
      if (eventType === 'thought_complete') {
        break;
      }
      
      const agentStep: AgentStep = {
        iteration: event.data.iteration ?? 0,
        action: event.data.action ?? 'thinking',
        tool: event.data.tool,
        success: event.data.success,
        inputPreview: event.data.input_preview,
        outputPreview: event.data.output_preview,
        content: event.data.content,
        timestamp: Date.now(),
      };

      if (isActive) {
        const msg = messages.find((m) => m.role === 'assistant' && m.isStreaming);
        if (msg) {
          const agentSteps = [...(msg.agentSteps || []), agentStep];
          const updates: Partial<ChatMessage> = { agentSteps };
          if (agentStep.action === 'thinking') {
            updates.thinkingContent = '';
          }
          const result = updateSessionState(messages, messageMap, updates);
          if (result) {
            return { messages: result.messages, messageMap: result.messageMap };
          }
        }
      } else {
        const cached = sessionCache.get(targetSessionId);
        if (cached) {
          const msg = cached.messages.find(
            (m) => m.role === 'assistant' && m.isStreaming
          );
          if (msg) {
            const agentSteps = [...(msg.agentSteps || []), agentStep];
            const updates: Partial<ChatMessage> = { agentSteps };
            if (agentStep.action === 'thinking') {
              updates.thinkingContent = '';
            }
            const result = updateSessionState(
              cached.messages,
              cached.messageMap,
              updates
            );
            if (result) {
              const newCache = new Map(sessionCache);
              newCache.set(targetSessionId, {
                ...cached,
                messages: result.messages,
                messageMap: result.messageMap,
              });
              return { sessionCache: newCache };
            }
          }
        }
      }
      break;
    }

    case 'complete': {
      const updates: Partial<ChatMessage> = {
        isStreaming: false,
        sql: event.data.sql,
        validationPassed: event.data.validation_passed,
      };

      const clarificationQuestions =
        event.data.clarification_questions || event.data.clarification?.questions;

      if (clarificationQuestions) {
        updates.clarificationQuestions = clarificationQuestions;
      }

      const newStatus =
        event.data.status === 'awaiting_clarification' || clarificationQuestions
          ? 'awaiting_clarification'
          : 'completed';

      if (isActive) {
        const msg = messages.find((m) => m.role === 'assistant' && m.isStreaming);
        if (!msg) {
          return { isLoading: false, status: 'completed' };
        }
        if (!updates.sql) updates.sql = msg.sql;

        const result = updateSessionState(messages, messageMap, updates);
        if (result) {
          return {
            messages: result.messages,
            messageMap: result.messageMap,
            isLoading: false,
            status: newStatus as QueryStatus,
          };
        }
      } else {
        const cached = sessionCache.get(targetSessionId);
        if (cached) {
          const msg = cached.messages.find(
            (m) => m.role === 'assistant' && m.isStreaming
          );
          if (msg && !updates.sql) updates.sql = msg.sql;

          const result = updateSessionState(
            cached.messages,
            cached.messageMap,
            updates
          );
          if (result) {
            const newCache = new Map(sessionCache);
            newCache.set(targetSessionId, {
              ...cached,
              messages: result.messages,
              messageMap: result.messageMap,
              status: newStatus as QueryStatus,
            });
            return { sessionCache: newCache };
          }
        }
      }
      break;
    }

    case 'error': {
      const errorMsg = event.data.error || 'Unknown error occurred';
      if (isActive) {
        return {
          isLoading: false,
          status: 'failed',
          error: errorMsg,
        };
      } else {
        const cached = sessionCache.get(targetSessionId);
        if (cached) {
          const newCache = new Map(sessionCache);
          newCache.set(targetSessionId, { ...cached, status: 'failed' });
          return { sessionCache: newCache };
        }
      }
      break;
    }
  }

  return {};
};
