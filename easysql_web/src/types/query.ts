export interface QueryRequest {
  question: string;
  db_name?: string;
  session_id?: string;
  stream?: boolean;
}

export interface ContinueRequest {
  answer: string;
  stream?: boolean;
}

export interface ClarificationInfo {
  questions: string[];
}

export type QueryStatus = 
  | 'pending'
  | 'processing'
  | 'awaiting_clarification'
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
}

export interface StreamEvent {
  event: 'start' | 'state_update' | 'agent_progress' | 'complete' | 'error';
  data: {
    node?: string;
    session_id?: string;
    message_id?: string;
    generated_sql?: string;
    status?: string;
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
    sql?: string;
    error?: string;
    type?: string;
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
}

export interface BranchRequest {
  from_message_id: string;
  question: string;
  stream?: boolean;
}

export interface MessageResponse {
  session_id: string;
  message_id?: string;
  status: QueryStatus;
  sql?: string;
  validation_passed?: boolean;
  error?: string;
}
