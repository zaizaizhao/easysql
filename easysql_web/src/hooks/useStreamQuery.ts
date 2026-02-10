import { useCallback, useRef } from 'react';
import {
  forkSessionFromMessage,
  getSessions,
  streamContinueQuery,
  streamFollowUpMessage,
  streamQuery,
} from '@/api';
import type { ChatMessage } from '@/types';
import { useChatStore } from '@/stores';
import { useAppStore } from '@/stores';

const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const isUuid = (value?: string): boolean => !!value && UUID_REGEX.test(value);

const collectBranchTurnIds = (
  messages: ChatMessage[],
  messageMap: Map<string, ChatMessage>,
  fromMessageId: string
): string[] => {
  const path: ChatMessage[] = [];
  let current = messageMap.get(fromMessageId);

  while (current) {
    path.unshift(current);
    if (!current.parentId) break;
    current = messageMap.get(current.parentId);
  }

  let turnIds = path
    .filter((message) => message.role === 'assistant' && !!message.turnId)
    .map((message) => message.turnId as string);

  if (turnIds.length <= 1) {
    const messageIndex = messages.findIndex((message) => message.id === fromMessageId);
    if (messageIndex >= 0) {
      turnIds = messages
        .slice(0, messageIndex + 1)
        .filter((message) => message.role === 'assistant' && !!message.turnId)
        .map((message) => message.turnId as string);
    }
  }

  return Array.from(new Set(turnIds));
};

export function useStreamQuery() {
  const abortControllerRef = useRef<AbortController | null>(null);
  
    const { 
    addMessage, 
    handleStreamEvent, 
    setIsLoading, 
    setError,
    isLoading,
    sessionId,
    threadId,
    messages,
  } = useChatStore();
  
  const { currentDatabase } = useAppStore();

  const sendQuery = useCallback(async (question: string) => {
    if (isLoading) return;
    
    setIsLoading(true);
    setError(null);

    const userMessageId = `user_${Date.now()}`;
    addMessage({
      id: userMessageId,
      role: 'user',
      content: question,
      timestamp: new Date(),
    });

    const assistantMessageId = `assistant_${Date.now()}`;
    addMessage({
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
    }, userMessageId);

    try {
      const generator = streamQuery(
        { 
          question, 
          db_name: currentDatabase || undefined,
          session_id: sessionId || undefined,
        }
      );

      for await (const event of generator) {
        handleStreamEvent(event);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to send query';
      setError(errorMessage);
      setIsLoading(false);
    }
  }, [isLoading, currentDatabase, sessionId, addMessage, handleStreamEvent, setIsLoading, setError]);

  const continueStream = useCallback(async (answer: string) => {
    if (isLoading || !sessionId) return;
    
    setIsLoading(true);
    setError(null);

    const state = useChatStore.getState();
    const lastMessage = state.messages[state.messages.length - 1];
    
    if (lastMessage && lastMessage.role === 'assistant') {
        useChatStore.getState().updateMessage(lastMessage.id, {
            userAnswer: answer,
            isStreaming: true
        });
    }

    try {
      const generator = streamContinueQuery(
        sessionId,
        { answer, thread_id: threadId || undefined }
      );

      for await (const event of generator) {
        handleStreamEvent(event);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to continue query';
      setError(errorMessage);
      setIsLoading(false);
    }
  }, [isLoading, sessionId, threadId, handleStreamEvent, setIsLoading, setError]);

  const sendFollowUp = useCallback(async (question: string, parentMessageId?: string) => {
    if (isLoading || !sessionId) return;
    
    setIsLoading(true);
    setError(null);

    const parentLocalId = parentMessageId || messages[messages.length - 1]?.id;
    const parentMessage = parentLocalId
      ? useChatStore.getState().messageMap.get(parentLocalId)
      : undefined;
    const parentServerId = parentMessage?.serverId;
    const parentMessageUuid = isUuid(parentServerId) ? parentServerId : undefined;
    const parentThreadId = parentMessage?.threadId || threadId || undefined;

    const userMessageId = `user_${Date.now()}`;
    addMessage({
      id: userMessageId,
      role: 'user',
      content: question,
      timestamp: new Date(),
    }, parentLocalId);

    const assistantMessageId = `assistant_${Date.now()}`;
    addMessage({
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
    }, userMessageId);

    try {
      const request = {
        question,
        thread_id: parentThreadId,
        ...(parentMessageUuid ? { parent_message_id: parentMessageUuid } : {}),
      };
      const generator = streamFollowUpMessage(sessionId, request);

      for await (const event of generator) {
        handleStreamEvent(event);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to send follow-up';
      setError(errorMessage);
      setIsLoading(false);
    }
  }, [isLoading, sessionId, threadId, messages, addMessage, handleStreamEvent, setIsLoading, setError]);

  const createBranch = useCallback(async (fromMessageId: string) => {
    if (isLoading || !sessionId) return null;
    
    setIsLoading(true);
    setError(null);

    const state = useChatStore.getState();
    const fromMessage = state.messageMap.get(fromMessageId);
    const fromServerId = fromMessage?.serverId || fromMessageId;
    const fromMessageUuid = isUuid(fromServerId) ? fromServerId : undefined;
    const fromThreadId = fromMessage?.threadId || threadId || undefined;
    const turnIds = collectBranchTurnIds(state.messages, state.messageMap, fromMessageId);

    try {
      const result = await forkSessionFromMessage(sessionId, {
        from_message_id: fromMessageUuid,
        thread_id: fromThreadId,
        turn_ids: turnIds,
      });

      try {
        const latestSessions = await getSessions();
        useChatStore.getState().setSessions(latestSessions.sessions);
      } catch (refreshError) {
        console.warn('Failed to refresh sessions after fork:', refreshError);
      }

      setIsLoading(false);
      return result.session_id;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to create branch';
      setError(errorMessage);
      setIsLoading(false);
      return null;
    }
  }, [isLoading, sessionId, threadId, setIsLoading, setError]);

  const cancelQuery = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);
  }, [setIsLoading]);

  return { sendQuery, continueStream, sendFollowUp, createBranch, cancelQuery };
}
