import { apiClient } from './client';
import type { ExecuteRequest, ExecuteResponse, SqlCheckResult } from '@/types';

export const executeApi = {
  executeSql: async (data: ExecuteRequest): Promise<ExecuteResponse> => {
    const response = await apiClient.post<ExecuteResponse>('/execute', data);
    return response.data;
  },

  checkSql: async (data: ExecuteRequest): Promise<SqlCheckResult> => {
    const response = await apiClient.post<SqlCheckResult>('/execute/check', data);
    return response.data;
  },
};
