export type ExecuteStatus = 'success' | 'failed' | 'timeout' | 'forbidden';

export interface ExecuteRequest {
  sql: string;
  db_name?: string;
  db_names?: string[];
  primary_db?: string;
  limit?: number;
  timeout?: number;
  allow_mutation?: boolean;
}

export interface ExecuteResponse {
  status: ExecuteStatus;
  data?: Record<string, unknown>[];
  columns?: string[];
  row_count: number;
  affected_rows?: number;
  execution_time_ms?: number;
  truncated: boolean;
  error?: string;
  db_names?: string[];
  primary_db?: string;
}

export interface SqlCheckResult {
  safe: boolean;
  is_mutation: boolean;
  statement_type: string;
  warnings: string[];
}
