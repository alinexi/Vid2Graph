"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "@/lib/store";
import { LAYER_META, type GraphNode } from "@/lib/types";
import { fmtTime } from "@/lib/utils";
import { Search } from "lucide-react";

export default function TranscriptPanel() {
  const { graph, currentTime, seekTo, selectNode, playing } = useStore();
  const seek = useStore((s) => s.seek);
  const [q, setQ] = useState("");
  const [follow, setFollow] = useState(true);
  const listRef = useRef<HTMLDivElement>(null);
  const userScrolled = useRef<number>(0);

  const segments = useMemo(() => graph?.transcript ?? [], [graph]);
  const activeIdx = useMemo(() => {
    let idx = -1;
    for (let i = 0; i < segments.length; i++) if (segments[i].start <= currentTime) idx = i; else break;
    return idx;
  }, [segments, currentTime]);

  // which nodes are mentioned inside each segment
  const mentionsBySeg = useMemo(() => {
    const map = new Map<number, GraphNode[]>();
    if (!graph) return map;
    for (const n of graph.nodes) {
      for (const m of n.mentions) {
        const seg = segments.find((s) => s.start <= m.start && m.start <= s.end + 0.6);
        if (!seg) continue;
        const arr = map.get(seg.id) ?? [];
        if (!arr.includes(n)) arr.push(n);
        map.set(seg.id, arr);
      }
    }
    return map;
  }, [graph, segments]);

  const filtered = useMemo(() => {
    if (!q.trim()) return segments;
    const needle = q.toLowerCase();
    return segments.filter((s) => s.text.toLowerCase().includes(needle));
  }, [segments, q]);

  // auto-scroll to the active segment while playing / after a seek
  useEffect(() => {
    if (!follow || q || activeIdx < 0) return;
    if (!playing && !seek) return;
    if (Date.now() - userScrolled.current < 2500) return;
    const el = listRef.current?.querySelector<HTMLElement>(`[data-seg="${activeIdx}"]`);
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeIdx, follow, q, playing, seek]);

  if (!graph) return <div className="flex flex-1 items-center justify-center text-sm muted">Transcript appears here</div>;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 border-b px-3 py-2" style={{ borderColor: "var(--border)" }}>
        <Search size={14} className="muted" />
        <input className="input" placeholder={`Search transcript (${segments.length} segments)`} value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="flex shrink-0 items-center gap-1 text-xs muted" title="Auto-scroll with playback">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> follow
        </label>
      </div>
      <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto px-2 py-2" onWheel={() => { userScrolled.current = Date.now(); }}>
        {filtered.map((s) => {
          const active = s.id === activeIdx;
          const nodes = mentionsBySeg.get(s.id) ?? [];
          return (
            <div
              key={s.id}
              data-seg={s.id}
              onClick={() => seekTo(s.start)}
              className={`group mb-1 cursor-pointer rounded-md px-2 py-1.5 text-[13px] leading-relaxed transition-colors ${active ? "bg-blue-500/15 ring-1 ring-blue-500/40" : "hover:bg-slate-500/10"}`}
            >
              <div className="flex gap-2">
                <span className={`mt-0.5 shrink-0 font-mono text-[11px] tabular-nums ${active ? "text-blue-500" : "muted"}`}>{fmtTime(s.start)}</span>
                <span className="flex-1">{highlight(s.text, q)}</span>
              </div>
              {nodes.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1 pl-12">
                  {nodes.map((n) => (
                    <button
                      key={n.id}
                      onClick={(e) => { e.stopPropagation(); selectNode(n.id, { seek: false }); seekTo(s.start); }}
                      className="pill hover:opacity-80"
                      style={{ borderColor: LAYER_META[n.layer].color, color: LAYER_META[n.layer].color }}
                      title={`${LAYER_META[n.layer].label}: open in graph`}
                    >
                      {n.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {filtered.length === 0 && <div className="p-4 text-center text-sm muted">No matches.</div>}
      </div>
    </div>
  );
}

function highlight(text: string, q: string) {
  if (!q.trim()) return text;
  const idx = text.toLowerCase().indexOf(q.toLowerCase());
  if (idx < 0) return text;
  return (<>{text.slice(0, idx)}<mark className="rounded bg-yellow-300/60 px-0.5 dark:bg-yellow-500/40">{text.slice(idx, idx + q.length)}</mark>{text.slice(idx + q.length)}</>);
}
