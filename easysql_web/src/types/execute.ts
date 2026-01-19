export type ExecuteStatus = 'success' | 'failed' | 'timeout' | 'forbidden';

export interface ExecuteRequest {
  sql: string;
  db_name: string;
  limit?: number;
  timeout?: number;
  allow_mutation?: boolean;
}

export interface ExecuteResponse {
  status: ExecuteStatus;
  data?: Record<string, any>[];
  columns?: string[];
  row_count: number;
  affected_rows?: number;
  execution_time_ms?: number;
  truncated: boolean;
  error?: string;
}

export interface SqlCheckResult {
  safe: boolean;
  is_mutation: boolean;
  statement_type: string;
  warnings: string[];
}
