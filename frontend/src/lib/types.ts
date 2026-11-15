export type Layer = "core" | "jargon" | "prerequisite";
export type Difficulty = "beginner" | "intermediate" | "advanced";
export type RelationType =
  | "prerequisite_for" | "compared_with" | "part_of" | "uses" | "leads_to"
  | "contrasts_with" | "example_of" | "related_to";
export type MediaKind = "youtube" | "video" | "audio" | "none";
export type GraphStatus = "pending" | "processing" | "ready" | "failed";

export interface TranscriptSegment { id: number; start: number; end: number; text: string; speaker?: string | null }
export interface Chunk { id: string; index: number; start: number; end: number; text: string; segment_ids: number[] }
export interface Mention { start: number; end?: number | null; snippet: string; chunk_id?: string | null }

export interface GraphNode {
  id: string;
  label: string;
  aliases: string[];
  layer: Layer;
  difficulty: Difficulty;
  eli5: string;
  summary: string;
  mentions: Mention[];
  chunk_ids: string[];
  expanded: boolean;
  inferred_from: string[];
}

export interface GraphEdge { id: string; source: string; target: string; relation: RelationType; label?: string | null }

export interface GraphStats {
  nodes: number; edges: number; core: number; jargon: number; prerequisite: number; merged: number; chunks: number; duration: number;
}

export interface GraphMeta {
  id: string;
  title: string;
  description: string;
  source_type: "youtube" | "upload" | "subtitle" | "demo";
  source_url?: string | null;
  media_kind: MediaKind;
  media_url?: string | null;
  duration: number;
  language: string;
  status: GraphStatus;
  model_used: string;
  created_at: string;
  updated_at: string;
  stats: GraphStats;
  is_demo: boolean;
}

export interface Graph extends GraphMeta {
  transcript: TranscriptSegment[];
  chunks: Chunk[];
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Job {
  id: string; graph_id: string; status: "queued" | "running" | "done" | "failed";
  stage: string; progress: number; message: string; error?: string | null; log: string[];
}

export interface ChatMessage { role: "user" | "assistant"; content: string; citations?: Citation[] }
export interface Citation { start: number; text: string }
export interface ChatResponse { answer: string; citations: Citation[]; context_chunks: string[] }
export interface ExpandResponse { graph: Graph; new_node_ids: string[]; new_edge_ids: string[] }

export interface ModelSettings {
  llm_provider: string; llm_model: string; llm_base_url: string; llm_api_key: string; llm_structured_mode: string;
  llm_temperature: number; llm_num_ctx: number;
  embedding_provider: string; embedding_model: string; embedding_base_url: string; embedding_api_key: string;
  merge_threshold: number;
  whisper_backend: string; whisper_model: string; whisper_device: string; whisper_compute_type: string;
  chunk_minutes: number; chunk_overlap_seconds: number;
}
export interface SettingsResponse {
  settings: ModelSettings; providers: string[]; whisper_backends: string[]; embedding_providers: string[];
}
export interface Probe { reachable: boolean; detail: string; provider?: string; model?: string; available_models?: string[]; backend?: string | null; resolved?: string | null; available?: Record<string, boolean> }
export interface Health { status: string; version: string; llm: Probe; embeddings: Probe; whisper: Probe; graphs: number }

export const LAYER_META: Record<Layer, { label: string; color: string; bg: string; ring: string; emoji: string; blurb: string }> = {
  core: { label: "Core Concept", color: "#3b82f6", bg: "bg-blue-500", ring: "ring-blue-500", emoji: "🔵", blurb: "Explicitly discussed or explained by the speaker" },
  jargon: { label: "Dropped Jargon", color: "#f97316", bg: "bg-orange-500", ring: "ring-orange-500", emoji: "🟠", blurb: "Mentioned in passing without a definition" },
  prerequisite: { label: "Implicit Prerequisite", color: "#a855f7", bg: "bg-purple-500", ring: "ring-purple-500", emoji: "🟣", blurb: "Never named in the video, but needed to follow it" },
};

export const DIFFICULTY_RANK: Record<Difficulty, number> = { beginner: 0, intermediate: 1, advanced: 2 };

export const RELATION_LABEL: Record<RelationType, string> = {
  prerequisite_for: "prerequisite for", compared_with: "compared with", part_of: "part of", uses: "uses",
  leads_to: "leads to", contrasts_with: "contrasts with", example_of: "example of", related_to: "related to",
};
