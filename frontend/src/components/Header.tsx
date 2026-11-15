"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import type { Health } from "@/lib/types";
import { Moon, Plus, RefreshCw, Settings, Sun } from "lucide-react";

export default function Header({ onSelectGraph, onRefresh }: { onSelectGraph: (id: string) => void; onRefresh: () => Promise<unknown> }) {
  const { graphs, graph, theme, setTheme, setIngestOpen, setSettingsOpen } = useStore();
  const [health, setHealth] = useState<Health | null>(null);
  const [healthErr, setHealthErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try { const h = await api.health(); if (alive) { setHealth(h); setHealthErr(null); } }
      catch (e) { if (alive) setHealthErr((e as Error).message); }
    };
    load();
    const id = setInterval(load, 30000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const llmOk = health?.llm.reachable && (health.llm as { model_available?: boolean }).model_available !== false;
  const dot = healthErr ? "bg-red-500" : !health ? "bg-slate-400" : llmOk ? "bg-emerald-500" : "bg-amber-500";
  const tip = healthErr ? healthErr : !health ? "Checking backend…" :
    `LLM ${health.llm.provider}:${health.llm.model} — ${health.llm.detail}\nEmbeddings: ${health.embeddings.backend ?? "?"} — ${health.embeddings.detail}\nWhisper: ${health.whisper.resolved ?? "none"}`;

  return (
    <header className="panel flex h-12 shrink-0 items-center gap-3 border-b px-3">
      <div className="flex items-center gap-2 font-semibold tracking-tight">
        <span className="text-base">🔵🟠🟣</span>
        <span>Vid2Graph</span>
      </div>
      <div className="mx-1 h-5 w-px" style={{ background: "var(--border)" }} />
      <select
        className="input max-w-xs"
        value={graph?.id ?? ""}
        onChange={(e) => e.target.value && onSelectGraph(e.target.value)}
        aria-label="Select graph"
      >
        {!graph && <option value="">— select a graph —</option>}
        {graphs.map((g) => (
          <option key={g.id} value={g.id}>
            {g.status !== "ready" ? `[${g.status}] ` : ""}{g.title}{g.is_demo ? " (demo)" : ""}
          </option>
        ))}
      </select>
      <button className="btn btn-ghost" title="Refresh list" onClick={() => onRefresh()}><RefreshCw size={15} /></button>
      <button className="btn btn-primary" onClick={() => setIngestOpen(true)}><Plus size={15} /> New graph</button>

      <div className="ml-auto flex items-center gap-2">
        <button className="btn btn-ghost gap-2" title={tip} onClick={() => setSettingsOpen(true)}>
          <span className={`inline-block h-2.5 w-2.5 rounded-full ${dot}`} />
          <span className="hidden text-xs muted md:inline">{health ? `${health.llm.provider} · ${health.llm.model}` : "backend"}</span>
        </button>
        <button className="btn btn-ghost" title="Model settings" onClick={() => setSettingsOpen(true)}><Settings size={16} /></button>
        <button className="btn btn-ghost" title="Toggle theme" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>
        <a className="btn btn-ghost text-xs muted" href="https://github.com/your-username/vid2graph" target="_blank" rel="noreferrer">GitHub</a>
      </div>
    </header>
  );
}
