export interface DatabaseInfo {
  name: string;
  type: string;
  host: string;
  port: number;
  database: string;
  description?: string;
}

export interface DatabaseList {
  databases: DatabaseInfo[];
  total: number;
}

export interface LLMConfig {
  query_mode: string;
  provider: string;
  model: string;
  planning_model?: string;
  max_sql_retries: number;
}

export interface RetrievalConfig {
  search_top_k: number;
  expand_fk: boolean;
  expand_max_depth: number;
  semantic_filter_enabled: boolean;
  semantic_filter_threshold: number;
  semantic_filter_min_tables: number;
  bridge_protection_enabled: boolean;
  bridge_max_hops: number;
  core_tables: string[];
  llm_filter_enabled: boolean;
  llm_filter_max_tables: number;
}

export interface EmbeddingConfig {
  provider: string;
  model: string;
  dimension: number;
}

export interface StorageConfig {
  neo4j_uri: string;
  neo4j_database: string;
  milvus_uri: string;
  milvus_collection_prefix: string;
}

export interface CodeContextConfig {
  enabled: boolean;
  search_top_k: number;
  score_threshold: number;
  max_snippets: number;
  supported_languages: string[];
}

export interface SystemConfig {
  llm: LLMConfig;
  retrieval: RetrievalConfig;
  embedding: EmbeddingConfig;
  storage: StorageConfig;
  code_context: CodeContextConfig;
  log_level: string;
}

export type PipelineStatus = 'idle' | 'running' | 'completed' | 'failed';

export interface PipelineStats {
  databases_processed: number;
  tables_extracted: number;
  columns_extracted: number;
  foreign_keys_extracted: number;
  neo4j_tables_written: number;
  neo4j_columns_written: number;
  neo4j_fks_written: number;
  milvus_tables_written: number;
  milvus_columns_written: number;
  errors: string[];
}

export interface PipelineStatusResponse {
  status: PipelineStatus;
  task_id?: string;
  started_at?: string;
  completed_at?: string;
  stats?: PipelineStats;
  error?: string;
}
