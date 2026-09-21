export interface DatabaseInfo {
  name: string;
  type: string;
  host: string;
  port: number;
  database: string;
  user?: string;
  schema?: string;
  system_type?: string;
  description?: string;
  dblink_connection_name?: string;
  has_password?: boolean;
}

export interface DatabaseList {
  databases: DatabaseInfo[];
  total: number;
}

export interface DatabaseConfigInput {
  name: string;
  type: 'postgresql' | 'mysql' | 'oracle' | 'sqlserver';
  host: string;
  port: number;
  user: string;
  password?: string;
  database: string;
  schema?: string;
  system_type?: string;
  description?: string;
}

export interface DatabaseConfigUpdateResponse extends DatabaseList {
  updated: string[];
}

export interface DatabaseConnectionTestResponse {
  success: boolean;
  message: string;
}

export type DatabaseQueryMode = 'single' | 'dblink';
export type DblinkStatusValue = 'not_required' | 'ready' | 'unavailable';

export interface DblinkRouteStatus {
  source_db: string;
  target_db: string;
  status: 'ready' | 'unavailable';
  reason: string;
}

export interface DatabaseDblinkStatus {
  name: string;
  connection_name: string;
  status: DblinkStatusValue;
  reason: string;
  extension_installed: boolean | null;
  connect_allowed: boolean | null;
  routes: DblinkRouteStatus[];
}

export interface DatabaseFederationStatus {
  mode: DatabaseQueryMode;
  status: DblinkStatusValue;
  reason: string;
  db_names: string[];
  databases: DatabaseDblinkStatus[];
}

export interface LLMConfig {
  query_mode: string;
  provider: string;
  model: string;
  planning_model?: string;
  temperature: number;
  use_agent_mode: boolean;
  agent_max_iterations: number;
  agent_timeout_seconds: number;
  query_timeout_seconds: number;
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
  project_namespace: string;
}

export interface CodeContextConfig {
  enabled: boolean;
  search_top_k: number;
  score_threshold: number;
  max_snippets: number;
  supported_languages: string[];
}

export interface SystemConfig {
  query_backend: 'adk' | 'langgraph';
  llm: LLMConfig;
  retrieval: RetrievalConfig;
  embedding: EmbeddingConfig;
  storage: StorageConfig;
  code_context: CodeContextConfig;
  log_level: string;
}

export type ConfigCategory = 'llm' | 'retrieval' | 'few_shot' | 'code_context' | 'langfuse';

export interface EditableConfigItem {
  value: string | number | boolean | null;
  is_secret: boolean;
  is_overridden: boolean;
  nullable: boolean;
  value_type: 'str' | 'int' | 'float' | 'bool' | 'null';
  settings_path: string;
  env_var: string;
  constraints: string[];
  invalidate_tags: string[];
}

export type EditableConfigResponse = Record<string, Record<string, EditableConfigItem>>;

export interface ConfigUpdateResponse {
  category: string;
  updated: string[];
  invalidate_tags: string[];
}

export interface ConfigDeleteResponse {
  category: string;
  deleted: number;
  message: string;
  invalidate_tags: string[];
}

export interface ConfigOverrideItem {
  value: string | number | boolean | null;
  is_secret: boolean;
  updated_at: string;
}

export type ConfigOverridesResponse = Record<string, Record<string, ConfigOverrideItem>>;

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
