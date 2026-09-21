import { apiClient } from './client';

export interface WikiDocument {
  id: string;
  source_key: string;
  revision: number;
  db_names: string[];
  index_status: string;
  index_error?: string;
  updated_at: string;
  page_count?: number;
  unchanged?: boolean;
}

export interface WikiPageCard {
  id: string;
  title: string;
  summary: string;
  domain: string;
  kind: string;
  table_ids: string[];
  source_key: string;
  source_line: number;
  revision: number;
  db_names: string[];
}

export interface WikiPage extends WikiPageCard {
  body_md: string;
  source_quote: string;
  join_rule?: Record<string, unknown>;
  next_offset?: number | null;
}

function scope(names: string[]) {
  const params = new URLSearchParams();
  names.forEach((name) => params.append('db_names', name));
  return params;
}

export const knowledgeApi = {
  async documents() {
    return (await apiClient.get<{ documents: WikiDocument[] }>('/knowledge/documents')).data;
  },
  async upload(file: File, names: string[]) {
    const body = new FormData();
    body.append('file', file);
    body.append('db_names', JSON.stringify(names));
    return (await apiClient.post<WikiDocument>('/knowledge/documents', body, {
      timeout: 420000,
      headers: { 'Content-Type': undefined },
    })).data;
  },
  async outline(names: string[], domain: string) {
    const params = scope(names);
    params.set('domain', domain);
    return (await apiClient.get<{ children: { domain: string; page_count: number }[] }>(
      '/knowledge/wiki', { params },
    )).data;
  },
  async pages(names: string[], domain: string, offset: number) {
    const params = scope(names);
    params.set('domain', domain);
    params.set('offset', String(offset));
    return (await apiClient.get<{ pages: WikiPageCard[]; next_offset: number | null }>(
      '/knowledge/pages', { params },
    )).data;
  },
  async read(id: string, names: string[], offset = 0) {
    const params = scope(names);
    params.set('offset', String(offset));
    return (await apiClient.get<WikiPage>(`/knowledge/pages/${id}`, { params })).data;
  },
  async search(q: string, names: string[]) {
    const params = scope(names);
    params.set('q', q);
    return (await apiClient.get<{ pages: WikiPageCard[]; mode: string }>(
      '/knowledge/search', { params },
    )).data;
  },
  async remove(id: string) {
    return (await apiClient.delete(`/knowledge/documents/${id}`)).data;
  },
  async reindex(id: string) {
    return (await apiClient.post<WikiDocument>(`/knowledge/documents/${id}/reindex`, {}, {
      timeout: 120000,
    })).data;
  },
  async revisions(id: string) {
    return (await apiClient.get<{ revisions: { revision: number; created_at: string }[] }>(
      `/knowledge/documents/${id}/revisions`,
    )).data;
  },
};
