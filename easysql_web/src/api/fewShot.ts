import { apiClient } from './client';

export interface FewShotCreateRequest {
  db_name: string;
  question: string;
  sql: string;
  tables_used?: string[];
  explanation?: string;
  message_id?: string;
}

export interface FewShotUpdateRequest {
  question?: string;
  sql?: string;
  tables_used?: string[];
  explanation?: string;
}

export interface FewShotInfo {
  id: string;
  db_name: string;
  question: string;
  sql: string;
  tables_used: string[];
  explanation: string | null;
  message_id: string | null;
  created_at: string;
}

export interface FewShotListResponse {
  items: FewShotInfo[];
  total: number;
  db_name: string;
}

export interface FewShotCheckResponse {
  is_few_shot: boolean;
  example_id: string | null;
  example: FewShotInfo | null;
}

export interface DuplicateErrorDetail {
  message: string;
  existing_id: string;
  similarity_score: number;
}

export const fewShotApi = {
  create: async (data: FewShotCreateRequest): Promise<FewShotInfo> => {
    const response = await apiClient.post<FewShotInfo>('/few-shot', data);
    return response.data;
  },

  list: async (
    dbName: string,
    limit = 100,
    offset = 0
  ): Promise<FewShotListResponse> => {
    const response = await apiClient.get<FewShotListResponse>('/few-shot', {
      params: { db_name: dbName, limit, offset },
    });
    return response.data;
  },

  getById: async (id: string): Promise<FewShotInfo> => {
    const response = await apiClient.get<FewShotInfo>(`/few-shot/${id}`);
    return response.data;
  },

  update: async (id: string, data: FewShotUpdateRequest): Promise<FewShotInfo> => {
    const response = await apiClient.put<FewShotInfo>(`/few-shot/${id}`, data);
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/few-shot/${id}`);
  },

  checkByMessageId: async (messageId: string): Promise<FewShotCheckResponse> => {
    const response = await apiClient.get<FewShotCheckResponse>(
      `/few-shot/by-message/${messageId}`
    );
    return response.data;
  },
};
