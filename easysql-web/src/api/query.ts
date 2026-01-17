import { apiClient, API_BASE_URL } from './client';
import type { QueryRequest, QueryResponse, ContinueRequest, StreamEvent } from '@/types';

export async function createQuery(request: QueryRequest): Promise<QueryResponse> {
  const response = await apiClient.post<QueryResponse>('/query', {
    ...request,
    stream: false,
  });
  return response.data;
}

export async function continueQuery(sessionId: string, request: ContinueRequest): Promise<QueryResponse> {
  const response = await apiClient.post<QueryResponse>(`/query/${sessionId}/continue`, request);
  return response.data;
}

export async function* streamContinueQuery(
  sessionId: string,
  request: ContinueRequest,
  onEvent?: (event: StreamEvent) => void
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${API_BASE_URL}/query/${sessionId}/continue`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...request, stream: true }),
  });

  yield* processStreamResponse(response, onEvent);
}

export async function* streamQuery(
  request: QueryRequest,
  onEvent?: (event: StreamEvent) => void
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${API_BASE_URL}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...request, stream: true }),
  });

  yield* processStreamResponse(response, onEvent);
}

async function* processStreamResponse(
  response: Response,
  onEvent?: (event: StreamEvent) => void
): AsyncGenerator<StreamEvent> {
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event: StreamEvent = JSON.parse(line.slice(6));
          onEvent?.(event);
          yield event;
        } catch {
          console.warn('Failed to parse SSE event:', line);
        }
      }
    }
  }
}
