import { create } from 'zustand';
import type { QueryStatus, StreamEvent } from '@/types';

export interface StepTrace {
  node: string;
  data?: any;
  timestamp: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  sql?: string;
  userAnswer?: string;
  validationPassed?: boolean;
  validationError?: string;
  clarificationQuestions?: string[];
  isStreaming?: boolean;
  steps?: string[]; // Deprecated, keep for compat
  trace?: StepTrace[];
  retrievalSummary?: {
    tablesCount: number;
    tables: string[];
  };
}

interface ChatState {
  sessionId: string | null;
  messages: ChatMessage[];
  status: QueryStatus;
  isLoading: boolean;
  error: string | null;

  setSessionId: (id: string | null) => void;
  addMessage: (message: ChatMessage) => void;
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void;
  setStatus: (status: QueryStatus) => void;
  setIsLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
  clearChat: () => void;
  handleStreamEvent: (event: StreamEvent) => void;
}

let messageIdCounter = 0;
const generateMessageId = () => `msg_${Date.now()}_${++messageIdCounter}`;

export const useChatStore = create<ChatState>((set, get) => ({
  sessionId: null,
  messages: [],
  status: 'pending',
  isLoading: false,
  error: null,

  setSessionId: (id) => set({ sessionId: id }),
  
  addMessage: (message) => set((state) => ({
    messages: [...state.messages, { ...message, id: message.id || generateMessageId() }],
  })),

  updateMessage: (id, updates) => set((state) => ({
    messages: state.messages.map((msg) =>
      msg.id === id ? { ...msg, ...updates } : msg
    ),
  })),

  setStatus: (status) => set({ status }),
  setIsLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),

  clearChat: () => set({
    sessionId: null,
    messages: [],
    status: 'pending',
    isLoading: false,
    error: null,
  }),

  handleStreamEvent: (event) => {
    const state = get();
    
    switch (event.event) {
      case 'start':
        set({ 
          sessionId: event.data.session_id || null,
          isLoading: true,
          status: 'processing',
        });
        break;

      case 'state_update': {
        const lastMessage = state.messages[state.messages.length - 1];
        if (lastMessage?.role === 'assistant' && lastMessage.isStreaming) {
          const updates: Partial<ChatMessage> = {};
          
          if (event.data.node) {
            const currentTrace = lastMessage.trace || [];
            const lastStep = currentTrace[currentTrace.length - 1];
            
            // Check if we are updating the existing last step or adding a new one
            if (lastStep?.node === event.data.node) {
                // Update existing step data
                 const updatedTrace = [...currentTrace];
                 updatedTrace[updatedTrace.length - 1] = {
                     ...lastStep,
                     data: { ...lastStep.data, ...event.data }
                 };
                 updates.trace = updatedTrace;
            } else {
                // Add new step
                updates.trace = [
                    ...currentTrace, 
                    { 
                        node: event.data.node, 
                        data: event.data, 
                        timestamp: Date.now() 
                    }
                ];
            }
          }

          if (event.data.generated_sql) {
            updates.sql = event.data.generated_sql;
          }
          if (event.data.clarification_questions) {
            updates.clarificationQuestions = event.data.clarification_questions;
          }
          if (event.data.retrieval_summary) {
            updates.retrievalSummary = {
              tablesCount: event.data.retrieval_summary.tables_count,
              tables: event.data.retrieval_summary.tables,
            };
          }
          
          if (Object.keys(updates).length > 0) {
            set((s) => ({
              messages: s.messages.map((msg) =>
                msg.id === lastMessage.id ? { ...msg, ...updates } : msg
              ),
            }));
          }
        }
        break;
      }

      case 'complete': {
        const lastMessage = state.messages[state.messages.length - 1];
        if (lastMessage?.role === 'assistant') {
          const updates: Partial<ChatMessage> = {
            isStreaming: false,
            sql: event.data.sql || lastMessage.sql,
            validationPassed: event.data.validation_passed,
          };

          // Fix: Handle nested clarification object from backend
          const clarificationQuestions = 
            event.data.clarification_questions || 
            event.data.clarification?.questions;

          if (clarificationQuestions) {
            updates.clarificationQuestions = clarificationQuestions;
          } else if (event.data.status === 'completed' || event.data.validation_passed) {
             // If completed successfully, we might want to clear questions 
             // to switch UI from "buttons" to "result"
             // But we keep them in 'updates' with undefined value to instruct zustand/react to remove?
             // Zustand partial update usually merges. We need to explicitly set it.
             // But Wait, if we are in "In-Place" mode, we want the buttons to disappear.
             // We will handle this by checking 'userAnswer'. If userAnswer exists, buttons are hidden.
             // So we don't strictly need to delete clarificationQuestions.
          }

          set((s) => ({
            messages: s.messages.map((msg) =>
              msg.id === lastMessage.id ? { ...msg, ...updates } : msg
            ),
            isLoading: false,
            // Check both explicit status and presence of questions
            status: (event.data.status === 'awaiting_clarification' || clarificationQuestions) 
              ? 'awaiting_clarification' 
              : 'completed',
          }));
        }
        break;
      }

      case 'error':
        set({
          isLoading: false,
          status: 'failed',
          error: event.data.error || 'Unknown error occurred',
        });
        break;
    }
  },
}));
