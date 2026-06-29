import type { Investigation, LogFile, Metrics, SearchResult } from "../types/api";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers }
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail ?? "Request failed");
  }
  return response.json() as Promise<T>;
}

export const api = {
  metrics: () => request<Metrics>("/metrics"),
  files: () => request<LogFile[]>("/files"),
  upload: (files: FileList) => {
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file));
    return request<{ files: LogFile[]; auto_loaded_demo_data: boolean }>("/upload", { method: "POST", body: form });
  },
  index: () => request<{ files_indexed: number; chunks_created: number; embeddings_stored: number }>("/index", { method: "POST" }),
  search: (query: string) => request<SearchResult[]>("/search", { method: "POST", body: JSON.stringify({ query, limit: 10 }) }),
  ask: (question: string) => request<Investigation>("/questions", { method: "POST", body: JSON.stringify({ question }) }),
  docker: (container: string) => request<{ files: LogFile[]; auto_loaded_demo_data: boolean }>(`/docker/${encodeURIComponent(container)}`, { method: "POST" })
};
