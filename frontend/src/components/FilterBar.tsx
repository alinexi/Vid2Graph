"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useStore, type Level } from "@/lib/store";
import { LAYER_META, type Layer } from "@/lib/types";
import { downloadBlob, filenameFromDisposition, fmtDuration } from "@/lib/utils";
import { ArrowDownToLine, ChevronDown, GitBranch, MessageSquare, Search, Trash2 } from "lucide-react";

const LEVELS: Level[] = ["beginner", "intermediate", "advanced"];
const LEVEL_HINT: Record<Level, string> = {
  beginner: "Show everything, including the full prerequisite scaffolding and ELI5 primers.",
  intermediate: "Hide beginner-level prerequisites you probably already know.",
  advanced: "Only novel material: hides basic terms and most prerequisites.",
};

export default function FilterBar({ onDeleted }: { onDeleted: () => void }) {
  const { graph, level, setLevel, search, setSearch, visibleLayers, toggleLayer, layoutDirection, setLayoutDirection, chatOpen, setChatOpen, notify } = useStore();
  const [exportOpen, setExportOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const doExport = async (format: "markdown" | "vault") => {
    if (!graph) return;
    setExportOpen(false);
    setBusy(true);
    try {
      const res = await fetch(api.exportUrl(graph.id, format));
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      const blob = await res.blob();
      downloadBlob(blob, filenameFromDisposition(res.headers.get("content-disposition"), `${graph.title}.${format === "vault" ? "zip" : "md"}`));
      notify("success", format === "vault" ? "Obsidian vault zip downloaded." : "Markdown downloaded.");
    } catch (e) { notify("error", (e as Error).message); } finally { setBusy(false); }
  };

  const del = async () => {
    if (!graph) return;
    if (!window.confirm(`Delete "${graph.title}"? This cannot be undone.`)) return;
    try { await api.deleteGraph(graph.id); notify("info", "Graph deleted."); onDeleted(); }
    catch (e) { notify("error", (e as Error).message); }
  };

  const counts = (l: Layer) => graph?.nodes.filter((n) => n.layer === l).length ?? 0;
  const levelIdx = LEVELS.indexOf(level);

  return (
    <div className="panel flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b px-3 py-2">
      <div className="min-w-0 max-w-[26rem]">
        <div className="truncate text-sm font-semibold" title={graph?.title}>{graph?.title ?? "—"}</div>
        {graph && (
          <div className="truncate text-[11px] muted">
            {fmtDuration(graph.duration)} · {graph.stats.nodes} nodes · {graph.stats.edges} edges · {graph.stats.merged} merged · {graph.model_used || "—"}
          </div>
        )}
      </div>

      <div className="relative">
        <Search size={13} className="muted absolute left-2 top-1/2 -translate-y-1/2" />
        <input className="input w-44 pl-7" placeholder="Search nodes…" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>

      <div className="flex items-center gap-2" title={LEVEL_HINT[level]}>
        <span className="text-[11px] font-semibold uppercase tracking-wide muted">Level</span>
        <input type="range" min={0} max={2} step={1} value={levelIdx} onChange={(e) => setLevel(LEVELS[Number(e.target.value)])} className="w-24 accent-blue-500" aria-label="Knowledge level" />
        <span className="w-24 text-xs capitalize">{level}</span>
      </div>

      <div className="flex items-center gap-1">
        {(["core", "jargon", "prerequisite"] as Layer[]).map((l) => (
          <button
            key={l} onClick={() => toggleLayer(l)}
            className={`pill transition-opacity ${visibleLayers[l] ? "" : "opacity-40 line-through"}`}
            style={{ borderColor: LAYER_META[l].color, color: LAYER_META[l].color }}
            title={`${LAYER_META[l].blurb} — click to toggle`}
          >
            {LAYER_META[l].label.split(" ")[0]} <span className="font-mono">{counts(l)}</span>
          </button>
        ))}
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        <button className="btn" title="Toggle layout direction" onClick={() => setLayoutDirection(layoutDirection === "LR" ? "TB" : "LR")}>
          <GitBranch size={14} className={layoutDirection === "LR" ? "rotate-90" : ""} /> {layoutDirection}
        </button>
        <button className={`btn ${chatOpen ? "btn-primary" : ""}`} onClick={() => setChatOpen(!chatOpen)} title="Graph-RAG chat"><MessageSquare size={14} /> Chat</button>
        <div className="relative">
          <button className="btn" disabled={!graph || busy} onClick={() => setExportOpen((v) => !v)}><ArrowDownToLine size={14} /> Export <ChevronDown size={12} /></button>
          {exportOpen && (
            <div className="panel absolute right-0 z-30 mt-1 w-64 rounded-lg border p-1 shadow-xl" onMouseLeave={() => setExportOpen(false)}>
              <button className="btn btn-ghost w-full justify-start" onClick={() => doExport("markdown")}>
                <div className="text-left"><div>Single Markdown file</div><div className="text-[11px] muted">Notion-ready, [[wiki-links]] + timestamps</div></div>
              </button>
              <button className="btn btn-ghost w-full justify-start" onClick={() => doExport("vault")}>
                <div className="text-left"><div>Obsidian vault (.zip)</div><div className="text-[11px] muted">One atomic note per concept + MOC index</div></div>
              </button>
            </div>
          )}
        </div>
        <button className="btn text-red-500" disabled={!graph} onClick={del} title="Delete graph"><Trash2 size={14} /></button>
      </div>
    </div>
  );
}
