import type { QueryStatus } from './query';

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
