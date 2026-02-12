import { apiClient } from './client';
import type {
  ConfigCategory,
  ConfigDeleteResponse,
  ConfigOverridesResponse,
  ConfigUpdateResponse,
  DatabaseList,
  EditableConfigResponse,
  PipelineStatusResponse,
  SystemConfig,
} from '@/types';

export async function getDatabases(): Promise<DatabaseList> {
  const response = await apiClient.get<DatabaseList>('/pipeline/databases');
  return response.data;
}

export async function getConfig(): Promise<SystemConfig> {
  const response = await apiClient.get<SystemConfig>('/config');
  return response.data;
}

export async function getPipelineStatus(): Promise<PipelineStatusResponse> {
  const response = await apiClient.get<PipelineStatusResponse>('/pipeline/status');
  return response.data;
}

export async function getEditableConfig(): Promise<EditableConfigResponse> {
  const response = await apiClient.get<EditableConfigResponse>('/config/editable');
  return response.data;
}

export async function getConfigOverrides(): Promise<ConfigOverridesResponse> {
  const response = await apiClient.get<ConfigOverridesResponse>('/config/overrides');
  return response.data;
}

export async function updateConfigCategory(
  category: ConfigCategory | string,
  updates: Record<string, string | number | boolean | null>,
): Promise<ConfigUpdateResponse> {
  const response = await apiClient.patch<ConfigUpdateResponse>(`/config/${category}`, updates);
  return response.data;
}

export async function resetConfigCategory(
  category: ConfigCategory | string,
): Promise<ConfigDeleteResponse> {
  const response = await apiClient.delete<ConfigDeleteResponse>(`/config/${category}`);
  return response.data;
}

export interface PipelineRunRequest {
  db_names?: string[];
  extract?: boolean;
  write_neo4j?: boolean;
  write_milvus?: boolean;
  drop_existing?: boolean;
}

export async function runPipeline(request: PipelineRunRequest = {}): Promise<{ task_id: string }> {
  const response = await apiClient.post<{ task_id: string; status: string }>('/pipeline/run', request);
  return response.data;
}

export async function checkHealth(): Promise<{ status: string }> {
  const response = await apiClient.get<{ status: string }>('/health');
  return response.data;
}
