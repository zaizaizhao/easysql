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
  steps?: string[];
  trace?: StepTrace[];
  retrievalSummary?: {
    tablesCount: number;
    tables: string[];
  };
  parentId?: string;
  childIds?: string[];
}

interface ChatState {
  sessionId: string | null;
  messages: ChatMessage[];
  messageMap: Map<string, ChatMessage>;
  activeBranchPath: string[];
  status: QueryStatus;
  isLoading: boolean;
  error: string | null;

  setSessionId: (id: string | null) => void;
  addMessage: (message: ChatMessage, parentId?: string) => void;
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void;
  setStatus: (status: QueryStatus) => void;
  setIsLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
  clearChat: () => void;
  handleStreamEvent: (event: StreamEvent) => void;
  
  getChildMessages: (parentId: string) => ChatMessage[];
  switchBranch: (messageId: string) => void;
  getVisibleMessages: () => ChatMessage[];
}

let messageIdCounter = 0;
const generateMessageId = () => `msg_${Date.now()}_${++messageIdCounter}`;

export const useChatStore = create<ChatState>((set, get) => ({
  sessionId: null,
  messages: [],
  messageMap: new Map(),
  activeBranchPath: [],
  status: 'pending',
  isLoading: false,
  error: null,

  setSessionId: (id) => set({ sessionId: id }),
  
  addMessage: (message, parentId) => set((state) => {
    const newMessage = { 
      ...message, 
      id: message.id || generateMessageId(),
      parentId,
      childIds: [],
    };
    
    const newMessages = [...state.messages, newMessage];
    const newMap = new Map(state.messageMap);
    newMap.set(newMessage.id, newMessage);
    
    if (parentId && newMap.has(parentId)) {
      const parent = newMap.get(parentId)!;
      const updatedParent = {
        ...parent,
        childIds: [...(parent.childIds || []), newMessage.id],
      };
      newMap.set(parentId, updatedParent);
      
      const parentIndex = newMessages.findIndex(m => m.id === parentId);
      if (parentIndex !== -1) {
        newMessages[parentIndex] = updatedParent;
      }
    }
    
    let newBranchPath = state.activeBranchPath;
    if (!parentId) {
      newBranchPath = [newMessage.id];
    } else if (state.activeBranchPath.includes(parentId)) {
      const parentIdx = state.activeBranchPath.indexOf(parentId);
      newBranchPath = [...state.activeBranchPath.slice(0, parentIdx + 1), newMessage.id];
    }
    
    return {
      messages: newMessages,
      messageMap: newMap,
      activeBranchPath: newBranchPath,
    };
  }),

  updateMessage: (id, updates) => set((state) => {
    const newMessages = state.messages.map((msg) =>
      msg.id === id ? { ...msg, ...updates } : msg
    );
    const newMap = new Map(state.messageMap);
    if (newMap.has(id)) {
      newMap.set(id, { ...newMap.get(id)!, ...updates });
    }
    return { messages: newMessages, messageMap: newMap };
  }),

  setStatus: (status) => set({ status }),
  setIsLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),

  clearChat: () => set({
    sessionId: null,
    messages: [],
    messageMap: new Map(),
    activeBranchPath: [],
    status: 'pending',
    isLoading: false,
    error: null,
  }),
  
  getChildMessages: (parentId) => {
    const state = get();
    return state.messages.filter(m => m.parentId === parentId);
  },
  
  switchBranch: (messageId) => set((state) => {
    const message = state.messageMap.get(messageId);
    if (!message) return state;
    
    const buildPath = (msgId: string): string[] => {
      const msg = state.messageMap.get(msgId);
      if (!msg) return [msgId];
      if (!msg.parentId) return [msgId];
      return [...buildPath(msg.parentId), msgId];
    };
    
    const pathToMessage = buildPath(messageId);
    
    const extendPath = (path: string[]): string[] => {
      const lastId = path[path.length - 1];
      const lastMsg = state.messageMap.get(lastId);
      if (!lastMsg || !lastMsg.childIds || lastMsg.childIds.length === 0) {
        return path;
      }
      return extendPath([...path, lastMsg.childIds[0]]);
    };
    
    return { activeBranchPath: extendPath(pathToMessage) };
  }),
  
  getVisibleMessages: () => {
    const state = get();
    if (state.activeBranchPath.length === 0) {
      return state.messages.filter(m => !m.parentId);
    }
    return state.activeBranchPath
      .map(id => state.messageMap.get(id))
      .filter((m): m is ChatMessage => m !== undefined);
  },

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
            set((s) => {
              const newMessages = s.messages.map((msg) =>
                msg.id === lastMessage.id ? { ...msg, ...updates } : msg
              );
              const newMap = new Map(s.messageMap);
              if (newMap.has(lastMessage.id)) {
                newMap.set(lastMessage.id, { ...newMap.get(lastMessage.id)!, ...updates });
              }
              return { messages: newMessages, messageMap: newMap };
            });
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
          }

          set((s) => {
            const newMessages = s.messages.map((msg) =>
              msg.id === lastMessage.id ? { ...msg, ...updates } : msg
            );
            const newMap = new Map(s.messageMap);
            if (newMap.has(lastMessage.id)) {
              newMap.set(lastMessage.id, { ...newMap.get(lastMessage.id)!, ...updates });
            }
            return {
              messages: newMessages,
              messageMap: newMap,
              isLoading: false,
              status: (event.data.status === 'awaiting_clarification' || clarificationQuestions) 
                ? 'awaiting_clarification' 
                : 'completed',
            };
          });
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
