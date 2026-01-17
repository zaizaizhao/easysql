import { useCallback, useRef } from 'react';
import { streamQuery, streamContinueQuery } from '@/api';
import { useChatStore } from '@/stores';
import { useAppStore } from '@/stores';

export function useStreamQuery() {
  const abortControllerRef = useRef<AbortController | null>(null);
  
  const { 
    addMessage, 
    handleStreamEvent, 
    setIsLoading, 
    setError,
    isLoading,
    sessionId,
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
    });

    try {
      const generator = streamQuery(
        { 
          question, 
          db_name: currentDatabase || undefined,
        },
        handleStreamEvent
      );

      for await (const event of generator) {
        handleStreamEvent(event);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to send query';
      setError(errorMessage);
      setIsLoading(false);
    }
  }, [isLoading, currentDatabase, addMessage, handleStreamEvent, setIsLoading, setError]);

  const continueStream = useCallback(async (answer: string) => {
    if (isLoading || !sessionId) return;
    
    setIsLoading(true);
    setError(null);

    // IN-PLACE UPDATE: Do not add new messages.
    // Instead, update the last assistant message (which asked the question).
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
        { answer },
        handleStreamEvent
      );

      for await (const event of generator) {
        handleStreamEvent(event);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to continue query';
      setError(errorMessage);
      setIsLoading(false);
    }
  }, [isLoading, sessionId, handleStreamEvent, setIsLoading, setError]);

  const cancelQuery = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);
  }, [setIsLoading]);

  return { sendQuery, continueStream, cancelQuery };
}
