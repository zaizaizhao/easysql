export interface SessionInfo {
  session_id: string;
  db_name?: string;
  status: string;
  created_at: string;
  updated_at: string;
  question_count: number;
}

export interface SessionList {
  sessions: SessionInfo[];
  total: number;
}

export interface MessageInfo {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}

export interface SessionDetail {
  session_id: string;
  db_name?: string;
  status: string;
  created_at: string;
  updated_at: string;
  raw_query?: string;
  generated_sql?: string;
  validation_passed?: boolean;
  messages: MessageInfo[];
  state?: Record<string, unknown>;
}
