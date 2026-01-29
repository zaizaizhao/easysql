export interface SessionInfo {
  session_id: string;
  db_name?: string;
  status: string;
  created_at: string;
  updated_at: string;
  question_count: number;
  title?: string;
}

export interface SessionList {
  sessions: SessionInfo[];
  total: number;
}

export type TurnStatus = 'in_progress' | 'awaiting_clarification' | 'completed' | 'failed';

export interface TurnClarification {
  questions: string[];
  answer?: string;
}

export interface TurnInfo {
  turn_id: string;
  question: string;
  status: TurnStatus;
  clarifications: TurnClarification[];
  final_sql?: string;
  validation_passed?: boolean;
  error?: string;
  created_at: string;
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
  turns: TurnInfo[];
  state?: Record<string, unknown>;
}
