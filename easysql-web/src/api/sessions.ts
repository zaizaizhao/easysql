import { apiClient } from './client';
import type { SessionList, SessionDetail } from '@/types';

export async function getSessions(limit = 100, offset = 0): Promise<SessionList> {
  const response = await apiClient.get<SessionList>('/sessions', {
    params: { limit, offset },
  });
  return response.data;
}

export async function getSessionDetail(sessionId: string): Promise<SessionDetail> {
  const response = await apiClient.get<SessionDetail>(`/sessions/${sessionId}`);
  return response.data;
}

export async function deleteSession(sessionId: string): Promise<void> {
  await apiClient.delete(`/sessions/${sessionId}`);
}
