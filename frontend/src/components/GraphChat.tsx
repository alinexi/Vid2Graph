"use client";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import { LAYER_META } from "@/lib/types";
import { fmtTime, parseTimestampTokens } from "@/lib/utils";
import { Eraser, Loader2, Send, X } from "lucide-react";

const SUGGESTIONS = ["How did the speaker compare these?", "Summarize what was said about this.", "Why does this matter in the talk?"];

export default function GraphChat() {
  const { graph, chatOpen, setChatOpen, chatSelection, toggleChatSelection, clearChatSelection, chatHistory, pushChat, resetChat, seekTo, notify } = useStore();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [chatHistory, busy]);

  if (!chatOpen || !graph) return null;
  const selected = chatSelection.map((id) => graph.nodes.find((n) => n.id === id)!).filter(Boolean);

  const ask = async (question: string) => {
    if (!question.trim() || !selected.length || busy) return;
    setQ("");
    pushChat({ role: "user", content: question });
    setBusy(true);
    try {
      const res = await api.chat(graph.id, chatSelection, question, chatHistory);
      pushChat({ role: "assistant", content: res.answer, citations: res.citations });
    } catch (e) {
      notify("error", (e as Error).message);
      pushChat({ role: "assistant", content: `⚠️ ${(e as Error).message}` });
    } finally { setBusy(false); }
  };

  return (
    <div className="panel absolute bottom-3 left-3 z-10 flex h-[26rem] w-[26rem] max-w-[calc(100%-1.5rem)] flex-col rounded-xl border shadow-2xl animate-fadeIn">
      <div className="flex items-center gap-2 border-b px-3 py-2" style={{ borderColor: "var(--border)" }}>
        <div className="text-sm font-semibold">Graph chat</div>
        <span className="text-[11px] muted">answers only from linked transcript chunks</span>
        <button className="btn btn-ghost ml-auto" title="Clear conversation" onClick={resetChat}><Eraser size={14} /></button>
        <button className="btn btn-ghost" onClick={() => setChatOpen(false)} aria-label="Close"><X size={14} /></button>
      </div>

      <div className="flex flex-wrap items-center gap-1 border-b px-3 py-2" style={{ borderColor: "var(--border)" }}>
        {selected.length === 0 && <span className="text-xs muted">Shift+click up to 3 nodes on the canvas (or use “Ask about this node”).</span>}
        {selected.map((n, i) => (
          <button key={n.id} className="pill hover:opacity-80" style={{ borderColor: LAYER_META[n.layer].color, color: LAYER_META[n.layer].color }} onClick={() => toggleChatSelection(n.id)} title="Remove">
            {i + 1}· {n.label} <X size={10} />
          </button>
        ))}
        {selected.length > 0 && <button className="ml-auto text-[11px] muted hover:underline" onClick={clearChatSelection}>clear</button>}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2 text-sm">
        {chatHistory.length === 0 && selected.length > 0 && (
          <div className="flex flex-col gap-1">
            {SUGGESTIONS.map((s) => <button key={s} className="btn btn-ghost justify-start text-xs muted" onClick={() => ask(s)}>“{s}”</button>)}
          </div>
        )}
        {chatHistory.map((m, i) => (
          <div key={i} className={`mb-2 flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[88%] rounded-xl px-3 py-2 ${m.role === "user" ? "bg-blue-600 text-white" : "bg-slate-500/10"}`}>
              {m.role === "user" ? m.content : <Answer text={m.content} onSeek={seekTo} />}
              {m.citations && m.citations.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1 border-t pt-1.5" style={{ borderColor: "var(--border)" }}>
                  {m.citations.map((c, j) => <button key={j} className="ts-pill" title={c.text} onClick={() => seekTo(c.start)}>{fmtTime(c.start)}</button>)}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && <div className="flex items-center gap-2 text-xs muted"><Loader2 size={12} className="animate-spin" /> thinking…</div>}
        <div ref={bottom} />
      </div>

      <form className="flex items-center gap-2 border-t p-2" style={{ borderColor: "var(--border)" }} onSubmit={(e) => { e.preventDefault(); ask(q); }}>
        <input className="input" placeholder={selected.length ? "Ask about the selected nodes…" : "Select nodes first"} value={q} onChange={(e) => setQ(e.target.value)} disabled={!selected.length || busy} />
        <button className="btn btn-primary" type="submit" disabled={!q.trim() || !selected.length || busy}><Send size={14} /></button>
      </form>
    </div>
  );
}

/** Renders markdown and turns [mm:ss] into clickable seek pills. */
function Answer({ text, onSeek }: { text: string; onSeek: (t: number) => void }) {
  return (
    <div className="prose-chat text-[13px] leading-relaxed">
      <ReactMarkdown components={{
        p: ({ children }) => <p>{withPills(children, onSeek)}</p>,
        li: ({ children }) => <li>{withPills(children, onSeek)}</li>,
      }}>{text}</ReactMarkdown>
    </div>
  );
}

function withPills(children: React.ReactNode, onSeek: (t: number) => void): React.ReactNode {
  const arr = Array.isArray(children) ? children : [children];
  return arr.map((c, i) => {
    if (typeof c !== "string") return <span key={i}>{c}</span>;
    return parseTimestampTokens(c).map((tok, j) =>
      tok.type === "ts" ? <button key={`${i}-${j}`} className="ts-pill mx-0.5" onClick={() => onSeek(tok.seconds!)}>{tok.value}</button> : <span key={`${i}-${j}`}>{tok.value}</span>);
  });
}
