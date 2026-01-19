import { apiClient, API_BASE_URL } from './client';
import type { SessionList, SessionDetail, SessionInfo, StreamEvent, MessageRequest, BranchRequest } from '@/types';

export interface CreateSessionRequest {
  db_name?: string;
}

export async function createSession(dbName?: string): Promise<SessionInfo> {
  const response = await apiClient.post<SessionInfo>('/sessions', { db_name: dbName });
  return response.data;
}

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

export async function* streamFollowUpMessage(
  sessionId: string,
  request: MessageRequest,
  onEvent?: (event: StreamEvent) => void
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...request, stream: true }),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event: StreamEvent = JSON.parse(line.slice(6));
          onEvent?.(event);
          yield event;
        } catch {
          continue;
        }
      }
    }
  }
}

export async function* streamBranchMessage(
  sessionId: string,
  request: BranchRequest,
  onEvent?: (event: StreamEvent) => void
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/branch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...request, stream: true }),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event: StreamEvent = JSON.parse(line.slice(6));
          onEvent?.(event);
          yield event;
        } catch {
          continue;
        }
      }
    }
  }
}
