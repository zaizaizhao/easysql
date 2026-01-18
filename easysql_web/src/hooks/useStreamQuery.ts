import { useCallback, useRef } from 'react';
import { streamQuery, streamContinueQuery, streamFollowUpMessage, streamBranchMessage } from '@/api';
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

  const sendFollowUp = useCallback(async (question: string, parentMessageId?: string) => {
    if (isLoading || !sessionId) return;
    
    setIsLoading(true);
    setError(null);

    const parentId = parentMessageId || messages[messages.length - 1]?.id;

    const userMessageId = `user_${Date.now()}`;
    addMessage({
      id: userMessageId,
      role: 'user',
      content: question,
      timestamp: new Date(),
    }, parentId);

    const assistantMessageId = `assistant_${Date.now()}`;
    addMessage({
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
    }, userMessageId);

    try {
      const generator = streamFollowUpMessage(
        sessionId,
        { question },
        handleStreamEvent
      );

      for await (const event of generator) {
        handleStreamEvent(event);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to send follow-up';
      setError(errorMessage);
      setIsLoading(false);
    }
  }, [isLoading, sessionId, messages, addMessage, handleStreamEvent, setIsLoading, setError]);

  const createBranch = useCallback(async (question: string, fromMessageId: string) => {
    if (isLoading || !sessionId) return;
    
    setIsLoading(true);
    setError(null);

    const userMessageId = `user_${Date.now()}`;
    addMessage({
      id: userMessageId,
      role: 'user',
      content: question,
      timestamp: new Date(),
    }, fromMessageId);

    const assistantMessageId = `assistant_${Date.now()}`;
    addMessage({
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
    }, userMessageId);

    try {
      const generator = streamBranchMessage(
        sessionId,
        { from_message_id: fromMessageId, question },
        handleStreamEvent
      );

      for await (const event of generator) {
        handleStreamEvent(event);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to create branch';
      setError(errorMessage);
      setIsLoading(false);
    }
  }, [isLoading, sessionId, addMessage, handleStreamEvent, setIsLoading, setError]);

  const cancelQuery = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);
  }, [setIsLoading]);

  return { sendQuery, continueStream, sendFollowUp, createBranch, cancelQuery };
}
