import { apiClient } from './client';
import type { DatabaseList, SystemConfig, PipelineStatusResponse } from '@/types';

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
