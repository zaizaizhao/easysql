import type { QueryStatus } from './query';

export interface StepTrace {
  node: string;
  data?: any;
  timestamp: number;
}

export interface AgentStep {
  iteration: number;
  action: 'tool_start' | 'tool_end' | 'thinking' | 'token' | 'thought_complete';
  tool?: string;
  success?: boolean;
  inputPreview?: string;
  outputPreview?: string;
  content?: string;
  timestamp: number;
}

export interface ChatMessage {
  id: string;
  serverId?: string;
  threadId?: string;
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
  agentSteps?: AgentStep[];
  thinkingContent?: string;
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
