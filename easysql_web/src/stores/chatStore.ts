import { create } from 'zustand';
import type { QueryStatus, StreamEvent, SessionInfo } from '@/types';

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

export interface SessionCache {
  sessionId: string;
  messages: ChatMessage[];
  messageMap: Map<string, ChatMessage>;
  activeBranchPath: string[];
  status: QueryStatus;
  title: string;
  updatedAt: Date;
}

interface ChatState {
  sessionId: string | null;
  messages: ChatMessage[];
  messageMap: Map<string, ChatMessage>;
  activeBranchPath: string[];
  status: QueryStatus;
  isLoading: boolean;
  error: string | null;

  sessions: SessionInfo[];
  sessionCache: Map<string, SessionCache>;
  isLoadingSessions: boolean;

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

  setSessions: (sessions: SessionInfo[]) => void;
  setIsLoadingSessions: (loading: boolean) => void;
  switchSession: (sessionId: string, messages?: ChatMessage[]) => void;
  cacheCurrentSession: () => void;
  removeSession: (sessionId: string) => void;
  getSessionTitle: (sessionId: string) => string;
  addNewSession: (session: SessionInfo) => void;
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

  sessions: [],
  sessionCache: new Map(),
  isLoadingSessions: false,

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
    const eventSessionId = event.data?.session_id;
    const targetSessionId = eventSessionId || state.sessionId;
    
    if (!targetSessionId) return;

    const isActive = targetSessionId === state.sessionId;

    // Helper to update a session's state (either active or cached)
    const updateSessionState = (
      currentMessages: ChatMessage[],
      currentMap: Map<string, ChatMessage>,
      updates: Partial<ChatMessage>,
    ) => {
      const streamingMessage = currentMessages.find(
        m => m.role === 'assistant' && m.isStreaming
      );
      
      if (!streamingMessage) return null;

      const newMessages = currentMessages.map((msg) =>
        msg.id === streamingMessage.id ? { ...msg, ...updates } : msg
      );
      
      const newMap = new Map(currentMap);
      if (newMap.has(streamingMessage.id)) {
        newMap.set(streamingMessage.id, { ...newMap.get(streamingMessage.id)!, ...updates });
      }

      return { messages: newMessages, messageMap: newMap };
    };

    switch (event.event) {
      case 'start': {
        if (isActive) {
          set({ 
            sessionId: targetSessionId,
            isLoading: true,
            status: 'processing',
          });
        } else {
          const cached = state.sessionCache.get(targetSessionId);
          if (cached) {
            const newCache = new Map(state.sessionCache);
            newCache.set(targetSessionId, { ...cached, status: 'processing' });
            set({ sessionCache: newCache });
          }
        }
        break;
      }

      case 'state_update': {
        const updates: Partial<ChatMessage> = {};
        
        if (event.data.node) {
          let currentTrace: StepTrace[] = [];
          
          if (isActive) {
             const msg = state.messages.find(m => m.role === 'assistant' && m.isStreaming);
             currentTrace = msg?.trace || [];
          } else {
             const cached = state.sessionCache.get(targetSessionId);
             const msg = cached?.messages.find(m => m.role === 'assistant' && m.isStreaming);
             currentTrace = msg?.trace || [];
          }

          const lastStep = currentTrace[currentTrace.length - 1];
          let updatedTrace = [...currentTrace];

          if (lastStep?.node === event.data.node) {
            updatedTrace[updatedTrace.length - 1] = {
              ...lastStep,
              data: { ...lastStep.data, ...event.data }
            };
          } else {
            updatedTrace.push({ 
              node: event.data.node, 
              data: event.data, 
              timestamp: Date.now() 
            });
          }
          updates.trace = updatedTrace;
        }

        if (event.data.generated_sql) updates.sql = event.data.generated_sql;
        if (event.data.clarification_questions) updates.clarificationQuestions = event.data.clarification_questions;
        if (event.data.retrieval_summary) {
          updates.retrievalSummary = {
            tablesCount: event.data.retrieval_summary.tables_count,
            tables: event.data.retrieval_summary.tables,
          };
        }
        
        if (Object.keys(updates).length > 0) {
          if (isActive) {
            const result = updateSessionState(state.messages, state.messageMap, updates);
            if (result) set({ messages: result.messages, messageMap: result.messageMap });
          } else {
            const cached = state.sessionCache.get(targetSessionId);
            if (cached) {
              const result = updateSessionState(cached.messages, cached.messageMap, updates);
              if (result) {
                const newCache = new Map(state.sessionCache);
                newCache.set(targetSessionId, { 
                  ...cached, 
                  messages: result.messages, 
                  messageMap: result.messageMap 
                });
                set({ sessionCache: newCache });
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
          event.data.clarification_questions || 
          event.data.clarification?.questions;

        if (clarificationQuestions) {
          updates.clarificationQuestions = clarificationQuestions;
        }

        const newStatus = (event.data.status === 'awaiting_clarification' || clarificationQuestions) 
          ? 'awaiting_clarification' 
          : 'completed';

        if (isActive) {
          const msg = state.messages.find(m => m.role === 'assistant' && m.isStreaming);
          if (!msg) {
             set({ isLoading: false, status: 'completed' });
             break;
          }
          if (!updates.sql) updates.sql = msg.sql;

          const result = updateSessionState(state.messages, state.messageMap, updates);
          if (result) {
            set({
              messages: result.messages,
              messageMap: result.messageMap,
              isLoading: false,
              status: newStatus as QueryStatus,
            });
          }
        } else {
          const cached = state.sessionCache.get(targetSessionId);
          if (cached) {
            const msg = cached.messages.find(m => m.role === 'assistant' && m.isStreaming);
            if (msg && !updates.sql) updates.sql = msg.sql;

            const result = updateSessionState(cached.messages, cached.messageMap, updates);
            if (result) {
              const newCache = new Map(state.sessionCache);
              newCache.set(targetSessionId, {
                ...cached,
                messages: result.messages,
                messageMap: result.messageMap,
                status: newStatus as QueryStatus,
              });
              set({ sessionCache: newCache });
            }
          }
        }
        break;
      }

      case 'error': {
        const errorMsg = event.data.error || 'Unknown error occurred';
        if (isActive) {
          set({
            isLoading: false,
            status: 'failed',
            error: errorMsg,
          });
        } else {
          const cached = state.sessionCache.get(targetSessionId);
          if (cached) {
            const newCache = new Map(state.sessionCache);
            newCache.set(targetSessionId, { ...cached, status: 'failed' });
            set({ sessionCache: newCache });
          }
        }
        break;
      }
    }
  },

  setSessions: (sessions) => set({ sessions }),
  
  setIsLoadingSessions: (loading) => set({ isLoadingSessions: loading }),

  cacheCurrentSession: () => set((state) => {
    if (!state.sessionId || state.messages.length === 0) return state;
    
    const firstUserMessage = state.messages.find(m => m.role === 'user');
    const title = firstUserMessage?.content.slice(0, 50) || `Session ${state.sessionId.slice(0, 8)}`;
    
    const newCache = new Map(state.sessionCache);
    newCache.set(state.sessionId, {
      sessionId: state.sessionId,
      messages: [...state.messages],
      messageMap: new Map(state.messageMap),
      activeBranchPath: [...state.activeBranchPath],
      status: state.status,
      title,
      updatedAt: new Date(),
    });
    
    return { sessionCache: newCache };
  }),

  switchSession: (sessionId, messages) => set((state) => {
    if (state.sessionId) {
      const firstUserMessage = state.messages.find(m => m.role === 'user');
      const title = firstUserMessage?.content.slice(0, 50) || `Session ${state.sessionId.slice(0, 8)}`;
      
      const newCache = new Map(state.sessionCache);
      newCache.set(state.sessionId, {
        sessionId: state.sessionId,
        messages: [...state.messages],
        messageMap: new Map(state.messageMap),
        activeBranchPath: [...state.activeBranchPath],
        status: state.status,
        title,
        updatedAt: new Date(),
      });
      
      const cached = newCache.get(sessionId);
      if (cached) {
        return {
          sessionCache: newCache,
          sessionId: cached.sessionId,
          messages: cached.messages,
          messageMap: cached.messageMap,
          activeBranchPath: cached.activeBranchPath,
          status: cached.status,
          isLoading: cached.status === 'processing',
          error: null,
        };
      }

      if (messages) {
        const messageMap = new Map<string, ChatMessage>();
        messages.forEach(m => messageMap.set(m.id, m));
        const branchPath = messages.map(m => m.id);
        
        return {
          sessionCache: newCache,
          sessionId,
          messages,
          messageMap,
          activeBranchPath: branchPath,
          status: 'completed',
          isLoading: false,
          error: null,
        };
      }

      return {
        sessionCache: newCache,
        sessionId,
        messages: [],
        messageMap: new Map(),
        activeBranchPath: [],
        status: 'pending',
        isLoading: false,
        error: null,
      };
    }

    const cached = state.sessionCache.get(sessionId);
    if (cached) {
      return {
        sessionId: cached.sessionId,
        messages: cached.messages,
        messageMap: cached.messageMap,
        activeBranchPath: cached.activeBranchPath,
        status: cached.status,
        isLoading: cached.status === 'processing',
        error: null,
      };
    }

    if (messages) {
      const messageMap = new Map<string, ChatMessage>();
      messages.forEach(m => messageMap.set(m.id, m));
      const branchPath = messages.map(m => m.id);
      
      return {
        sessionId,
        messages,
        messageMap,
        activeBranchPath: branchPath,
        status: 'completed',
        isLoading: false,
        error: null,
      };
    }

    return {
      sessionId,
      messages: [],
      messageMap: new Map(),
      activeBranchPath: [],
      status: 'pending',
      isLoading: false,
      error: null,
    };
  }),

  removeSession: (sessionId) => set((state) => {
    const newCache = new Map(state.sessionCache);
    newCache.delete(sessionId);
    
    const newSessions = state.sessions.filter(s => s.session_id !== sessionId);
    
    if (state.sessionId === sessionId) {
      return {
        sessionCache: newCache,
        sessions: newSessions,
        sessionId: null,
        messages: [],
        messageMap: new Map(),
        activeBranchPath: [],
        status: 'pending',
        isLoading: false,
        error: null,
      };
    }
    
    return { sessionCache: newCache, sessions: newSessions };
  }),

  getSessionTitle: (sessionId) => {
    const state = get();
    const cached = state.sessionCache.get(sessionId);
    if (cached) return cached.title;
    
    const session = state.sessions.find(s => s.session_id === sessionId);
    if (session) {
      return `Session ${session.session_id.slice(0, 8)}`;
    }
    
    return `Session ${sessionId.slice(0, 8)}`;
  },

  addNewSession: (session) => set((state) => {
    const existingIndex = state.sessions.findIndex(s => s.session_id === session.session_id);
    const newSessions = existingIndex >= 0
      ? state.sessions
      : [session, ...state.sessions];
    
    return {
      sessionId: session.session_id,
      sessions: newSessions,
      messages: [],
      messageMap: new Map(),
      activeBranchPath: [],
      status: 'pending',
      isLoading: false,
      error: null,
    };
  }),
}));
