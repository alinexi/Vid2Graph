"use client";
import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import { LAYER_META, RELATION_LABEL } from "@/lib/types";
import { fmtTime } from "@/lib/utils";
import { ArrowRight, Loader2, MessageSquarePlus, Sparkles, X } from "lucide-react";

export default function NodeDrawer() {
  const { graph, selectedNodeId, drawerOpen, setDrawerOpen, seekTo, selectNode, toggleChatSelection, chatSelection, patchGraph, setHighlighted, notify } = useStore();
  const [expanding, setExpanding] = useState(false);
  const node = useMemo(() => graph?.nodes.find((n) => n.id === selectedNodeId) ?? null, [graph, selectedNodeId]);

  const connections = useMemo(() => {
    if (!graph || !node) return [];
    const byId = new Map(graph.nodes.map((n) => [n.id, n]));
    const out: Array<{ id: string; label: string; layer: keyof typeof LAYER_META; text: string }> = [];
    for (const e of graph.edges) {
      if (e.source === node.id && byId.has(e.target)) { const t = byId.get(e.target)!; out.push({ id: t.id, label: t.label, layer: t.layer, text: `${RELATION_LABEL[e.relation]} →` }); }
      else if (e.target === node.id && byId.has(e.source)) { const s = byId.get(e.source)!; out.push({ id: s.id, label: s.label, layer: s.layer, text: `← ${RELATION_LABEL[e.relation]}` }); }
    }
    return out;
  }, [graph, node]);

  if (!drawerOpen || !graph || !node) return null;
  const meta = LAYER_META[node.layer];
  const mentions = node.mentions.slice().sort((a, b) => a.start - b.start);
  const inChat = chatSelection.includes(node.id);

  const expand = async () => {
    setExpanding(true);
    try {
      const res = await api.expandNode(graph.id, node.id);
      patchGraph({ nodes: res.graph.nodes, edges: res.graph.edges, stats: res.graph.stats });
      setHighlighted(res.new_node_ids);
      notify(res.new_node_ids.length ? "success" : "info",
        res.new_node_ids.length ? `Added ${res.new_node_ids.length} deeper prerequisite${res.new_node_ids.length > 1 ? "s" : ""}.` : "Nothing new — the suggested prerequisites were already in the graph.");
    } catch (e) { notify("error", (e as Error).message); } finally { setExpanding(false); }
  };

  return (
    <aside className="panel absolute inset-y-0 right-0 z-10 flex w-[360px] max-w-[92%] flex-col border-l shadow-2xl animate-fadeIn">
      <div className="flex items-start gap-2 border-b p-4" style={{ borderColor: "var(--border)" }}>
        <span className="mt-1 h-10 w-1.5 shrink-0 rounded-full" style={{ background: meta.color }} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
            <span className="pill" style={{ borderColor: meta.color, color: meta.color }}>{meta.emoji} {meta.label}</span>
            <span className="pill capitalize">{node.difficulty}</span>
            {node.expanded && <span className="pill text-purple-400"><Sparkles size={10} /> expanded</span>}
          </div>
          <h2 className="mt-1.5 text-lg font-semibold leading-tight">{node.label}</h2>
          {node.aliases.length > 0 && <p className="mt-0.5 text-xs muted">Also: {node.aliases.join(", ")}</p>}
        </div>
        <button className="btn btn-ghost" onClick={() => setDrawerOpen(false)} aria-label="Close"><X size={16} /></button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4 text-sm">
        <p className="mb-3 text-[11px] muted">{meta.blurb}.</p>

        {node.eli5 && (
          <section className="mb-4">
            <h3 className="label">ELI5 primer</h3>
            <p className="leading-relaxed">{node.eli5}</p>
          </section>
        )}
        {node.summary && (
          <section className="mb-4">
            <h3 className="label">In this video</h3>
            <p className="leading-relaxed">{node.summary}</p>
          </section>
        )}

        <section className="mb-4">
          <h3 className="label">Timestamps {mentions.length > 0 && <span className="muted">({mentions.length})</span>}</h3>
          {mentions.length === 0 ? (
            <p className="text-xs muted">Never named in the video — inferred as a prerequisite{node.inferred_from.length ? " for:" : "."}</p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {mentions.map((m, i) => (
                <button key={i} onClick={() => seekTo(m.start)} className="group flex items-start gap-2 rounded-md border px-2 py-1.5 text-left hover:bg-blue-500/10" style={{ borderColor: "var(--border)" }}>
                  <span className="ts-pill shrink-0">{fmtTime(m.start)}</span>
                  <span className="line-clamp-2 text-xs muted group-hover:text-[color:var(--text)]">{m.snippet || "jump to mention"}</span>
                </button>
              ))}
            </div>
          )}
          {node.inferred_from.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {node.inferred_from.map((id) => { const t = graph.nodes.find((n) => n.id === id); return t ? (
                <button key={id} className="pill hover:opacity-80" style={{ borderColor: LAYER_META[t.layer].color, color: LAYER_META[t.layer].color }} onClick={() => selectNode(t.id)}>{t.label}</button>
              ) : null; })}
            </div>
          )}
        </section>

        {connections.length > 0 && (
          <section className="mb-4">
            <h3 className="label">Connections ({connections.length})</h3>
            <ul className="flex flex-col gap-1">
              {connections.map((c, i) => (
                <li key={i}>
                  <button className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-xs hover:bg-slate-500/10" onClick={() => selectNode(c.id)}>
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: LAYER_META[c.layer].color }} />
                    <span className="muted">{c.text}</span>
                    <span className="truncate font-medium">{c.label}</span>
                    <ArrowRight size={12} className="ml-auto shrink-0 muted" />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      <div className="flex flex-col gap-2 border-t p-3" style={{ borderColor: "var(--border)" }}>
        <button className="btn btn-primary justify-center" disabled={expanding} onClick={expand} title="Ask the model for deeper foundational prerequisites of this concept">
          {expanding ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} Generate deeper prerequisites
        </button>
        <button className={`btn justify-center ${inChat ? "border-emerald-500 text-emerald-500" : ""}`} onClick={() => toggleChatSelection(node.id)}>
          <MessageSquarePlus size={14} /> {inChat ? "Remove from chat selection" : "Ask about this node"}
        </button>
      </div>
    </aside>
  );
}
