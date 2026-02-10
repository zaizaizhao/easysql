import type { VizPlan } from './chart';

export interface QueryRequest {
  question: string;
  db_name?: string;
  session_id?: string;
  stream?: boolean;
}

export interface ContinueRequest {
  answer: string;
  stream?: boolean;
  thread_id?: string;
}

export interface ClarificationInfo {
  questions: string[];
}

export type QueryStatus = 
  | 'pending'
  | 'processing'
  | 'awaiting_clarify'
  | 'completed'
  | 'failed';

export interface QueryResponse {
  session_id: string;
  status: QueryStatus;
  sql?: string;
  validation_passed?: boolean;
  validation_error?: string;
  clarification?: ClarificationInfo;
  error?: string;
  stats?: Record<string, unknown>;
  message_id?: string;
  parent_message_id?: string;
  thread_id?: string;
  turn_id?: string;
}

export interface StreamEvent {
  event: 'start' | 'state_update' | 'agent_progress' | 'complete' | 'error';
  data: {
    node?: string;
    session_id?: string;
    thread_id?: string;
    message_id?: string;
    parent_message_id?: string;
    turn_id?: string;
    generated_sql?: string;
    status?: QueryStatus;
    validation_passed?: boolean;
    validation_result?: {
      valid: boolean;
      details?: string;
      error?: string;
    };
    clarification_questions?: string[];
    clarification?: {
      questions: string[];
    };
    retrieval_summary?: {
      tables_count: number;
      tables: string[];
    };
    context_summary?: {
      total_tokens: number;
      has_system_prompt: boolean;
      has_user_prompt: boolean;
    };
    chart_plan?: VizPlan;
    chart_reasoning?: string;
    sql?: string;
    error?: string;
    type?: 'tool_start' | 'tool_end' | 'thinking' | 'token' | 'thought_complete';
    iteration?: number;
    action?: 'tool_start' | 'tool_end' | 'thinking';
    tool?: string;
    success?: boolean;
    input_preview?: string;
    output_preview?: string;
    content?: string;
  };
}

export interface MessageRequest {
  question: string;
  stream?: boolean;
  parent_message_id?: string;
  thread_id?: string;
}

export interface BranchRequest {
  from_message_id: string;
  question: string;
  stream?: boolean;
  thread_id?: string;
}

export interface ForkSessionRequest {
  from_message_id?: string;
  thread_id?: string;
  turn_ids?: string[];
}

export interface ForkSessionResponse extends QueryResponse {
  source_session_id: string;
  cloned_turn_ids: string[];
}

export interface MessageResponse {
  session_id: string;
  message_id?: string;
  parent_message_id?: string;
  thread_id?: string;
  status: QueryStatus;
  sql?: string;
  validation_passed?: boolean;
  error?: string;
}
