import type { ChatMessage, ChatResponse, ExpandResponse, Graph, GraphMeta, Health, Job, ModelSettings, Probe, SettingsResponse } from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, `Cannot reach the Vid2Graph backend at ${API_URL}. Is it running? (make backend)`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j); } catch { /* ignore */ }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const json = (body: unknown, method = "POST"): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

export const api = {
  health: () => request<Health>("/api/health"),
  getSettings: () => request<SettingsResponse>("/api/settings"),
  saveSettings: (values: Partial<ModelSettings>) => request<{ settings: ModelSettings }>("/api/settings", json(values, "PUT")),
  testSettings: (values?: Partial<ModelSettings>) => request<{ llm: Probe; embeddings: Probe; whisper: Probe }>("/api/settings/test", json(values ?? null)),

  listGraphs: () => request<GraphMeta[]>("/api/graphs"),
  getGraph: (id: string) => request<Graph>(`/api/graphs/${id}`),
  deleteGraph: (id: string) => request<{ deleted: string }>(`/api/graphs/${id}`, { method: "DELETE" }),
  patchGraph: (id: string, body: Partial<Pick<GraphMeta, "title" | "description" | "media_url">>) =>
    request<GraphMeta>(`/api/graphs/${id}`, json(body, "PATCH")),
  resetDemo: () => request<Graph>("/api/demo/reset", { method: "POST" }),

  ingest: (form: FormData) => request<{ job_id: string; graph_id: string }>("/api/ingest", { method: "POST", body: form }),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
  getGraphJob: (graphId: string) => request<Job | null>(`/api/graphs/${graphId}/job`),

  expandNode: (graphId: string, nodeId: string) => request<ExpandResponse>(`/api/graphs/${graphId}/nodes/${nodeId}/expand`, { method: "POST" }),
  chat: (graphId: string, node_ids: string[], question: string, history: ChatMessage[]) =>
    request<ChatResponse>(`/api/graphs/${graphId}/chat`, json({ node_ids, question, history: history.map(({ role, content }) => ({ role, content })) })),

  exportUrl: (graphId: string, format: "markdown" | "vault") => `${API_URL}/api/graphs/${graphId}/export?format=${format}`,
  mediaUrl: (path: string) => (path.startsWith("http") ? path : `${API_URL}${path}`),
};
