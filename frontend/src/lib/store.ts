"use client";
import { create } from "zustand";
import type { ChatMessage, Difficulty, Graph, GraphMeta, GraphNode, Layer } from "./types";
import { DIFFICULTY_RANK } from "./types";

export type Level = Difficulty;

interface State {
  graphs: GraphMeta[];
  graph: Graph | null;
  loadingGraph: boolean;
  error: string | null;

  currentTime: number;
  playing: boolean;
  seek: { time: number; nonce: number } | null;

  selectedNodeId: string | null;
  chatSelection: string[];
  highlightedNodeIds: string[];
  level: Level;
  search: string;
  visibleLayers: Record<Layer, boolean>;
  layoutDirection: "LR" | "TB";

  drawerOpen: boolean;
  chatOpen: boolean;
  chatHistory: ChatMessage[];
  ingestOpen: boolean;
  settingsOpen: boolean;
  theme: "dark" | "light";
  toast: { kind: "info" | "error" | "success"; text: string } | null;

  setGraphs: (g: GraphMeta[]) => void;
  setGraph: (g: Graph | null) => void;
  patchGraph: (patch: Partial<Graph>) => void;
  setLoadingGraph: (v: boolean) => void;
  setError: (e: string | null) => void;
  setCurrentTime: (t: number) => void;
  setPlaying: (p: boolean) => void;
  seekTo: (t: number) => void;
  selectNode: (id: string | null, opts?: { seek?: boolean }) => void;
  toggleChatSelection: (id: string) => void;
  clearChatSelection: () => void;
  setHighlighted: (ids: string[]) => void;
  setLevel: (l: Level) => void;
  setSearch: (s: string) => void;
  toggleLayer: (l: Layer) => void;
  setLayoutDirection: (d: "LR" | "TB") => void;
  setDrawerOpen: (v: boolean) => void;
  setChatOpen: (v: boolean) => void;
  pushChat: (m: ChatMessage) => void;
  resetChat: () => void;
  setIngestOpen: (v: boolean) => void;
  setSettingsOpen: (v: boolean) => void;
  setTheme: (t: "dark" | "light") => void;
  notify: (kind: "info" | "error" | "success", text: string) => void;
}

export const useStore = create<State>((set, get) => ({
  graphs: [],
  graph: null,
  loadingGraph: false,
  error: null,
  currentTime: 0,
  playing: false,
  seek: null,
  selectedNodeId: null,
  chatSelection: [],
  highlightedNodeIds: [],
  level: "beginner",
  search: "",
  visibleLayers: { core: true, jargon: true, prerequisite: true },
  layoutDirection: "LR",
  drawerOpen: false,
  chatOpen: false,
  chatHistory: [],
  ingestOpen: false,
  settingsOpen: false,
  theme: "dark",
  toast: null,

  setGraphs: (graphs) => set({ graphs }),
  setGraph: (graph) => set({ graph, selectedNodeId: null, chatSelection: [], chatHistory: [], drawerOpen: false, currentTime: 0, playing: false, seek: null, highlightedNodeIds: [] }),
  patchGraph: (patch) => set((s) => (s.graph ? { graph: { ...s.graph, ...patch } } : {})),
  setLoadingGraph: (loadingGraph) => set({ loadingGraph }),
  setError: (error) => set({ error }),
  setCurrentTime: (currentTime) => set({ currentTime }),
  setPlaying: (playing) => set({ playing }),
  seekTo: (time) => set((s) => ({ seek: { time, nonce: (s.seek?.nonce ?? 0) + 1 }, currentTime: time })),
  selectNode: (id, opts) => {
    const g = get().graph;
    set({ selectedNodeId: id, drawerOpen: !!id });
    if (id && opts?.seek !== false && g) {
      const n = g.nodes.find((x) => x.id === id);
      const first = n?.mentions.slice().sort((a, b) => a.start - b.start)[0];
      if (first) get().seekTo(first.start);
    }
  },
  toggleChatSelection: (id) => set((s) => {
    const has = s.chatSelection.includes(id);
    if (has) return { chatSelection: s.chatSelection.filter((x) => x !== id) };
    if (s.chatSelection.length >= 3) return { toast: { kind: "info", text: "Select at most 3 nodes for chat." } };
    return { chatSelection: [...s.chatSelection, id], chatOpen: true };
  }),
  clearChatSelection: () => set({ chatSelection: [] }),
  setHighlighted: (highlightedNodeIds) => set({ highlightedNodeIds }),
  setLevel: (level) => set({ level }),
  setSearch: (search) => set({ search }),
  toggleLayer: (l) => set((s) => ({ visibleLayers: { ...s.visibleLayers, [l]: !s.visibleLayers[l] } })),
  setLayoutDirection: (layoutDirection) => set({ layoutDirection }),
  setDrawerOpen: (drawerOpen) => set({ drawerOpen }),
  setChatOpen: (chatOpen) => set({ chatOpen }),
  pushChat: (m) => set((s) => ({ chatHistory: [...s.chatHistory, m] })),
  resetChat: () => set({ chatHistory: [] }),
  setIngestOpen: (ingestOpen) => set({ ingestOpen }),
  setSettingsOpen: (settingsOpen) => set({ settingsOpen }),
  setTheme: (theme) => set({ theme }),
  notify: (kind, text) => {
    set({ toast: { kind, text } });
    setTimeout(() => { if (get().toast?.text === text) set({ toast: null }); }, kind === "error" ? 7000 : 3500);
  },
}));

/**
 * Knowledge-level filter.
 *  - beginner:     show everything, including the full prerequisite scaffolding.
 *  - intermediate: hide beginner-level prerequisites (assumed known).
 *  - advanced:     hide all beginner-level nodes and non-advanced prerequisites — only novel material remains.
 */
export function nodeVisible(n: GraphNode, level: Level, search: string, visibleLayers: Record<Layer, boolean>): boolean {
  if (!visibleLayers[n.layer]) return false;
  const rank = DIFFICULTY_RANK[n.difficulty];
  if (level === "intermediate" && n.layer === "prerequisite" && rank === 0) return false;
  if (level === "advanced") {
    if (rank === 0) return false;
    if (n.layer === "prerequisite" && rank < 2) return false;
  }
  if (search.trim()) {
    const q = search.toLowerCase();
    const hay = [n.label, ...n.aliases, n.eli5, n.summary].join(" ").toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}
