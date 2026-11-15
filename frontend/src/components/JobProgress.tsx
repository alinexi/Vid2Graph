"use client";
import type { Job } from "@/lib/types";
import { Loader2, X } from "lucide-react";

const STAGES = ["ingest", "chunk", "extract", "resolve", "enrich", "synthesize", "done"];

export default function JobProgress({ job, onDismiss }: { job: Job; onDismiss: () => void }) {
  const pct = Math.round(job.progress * 100);
  const idx = Math.max(0, STAGES.indexOf(job.stage));
  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/30 backdrop-blur-[2px]">
      <div className="panel w-full max-w-lg rounded-2xl border p-6 shadow-2xl">
        <div className="flex items-center justify-between">
          <h3 className="flex items-center gap-2 font-semibold">
            {job.status === "failed" ? "Processing failed" : <><Loader2 size={16} className="animate-spin" /> Building knowledge graph…</>}
          </h3>
          <button className="btn btn-ghost" onClick={onDismiss} aria-label="Hide"><X size={16} /></button>
        </div>
        <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
          <div className="h-full rounded-full bg-gradient-to-r from-purple-500 via-orange-500 to-blue-500 transition-all" style={{ width: `${pct}%` }} />
        </div>
        <div className="mt-2 flex justify-between text-xs muted">
          <span className="truncate">{job.message}</span><span>{pct}%</span>
        </div>
        <ol className="mt-4 flex flex-wrap gap-1.5 text-[11px]">
          {STAGES.map((s, i) => (
            <li key={s} className={`pill ${i < idx ? "border-emerald-500/50 text-emerald-500" : i === idx ? "border-blue-500 text-blue-500" : "muted"}`}>{s}</li>
          ))}
        </ol>
        {job.error && <p className="mt-3 rounded-md border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-500">{job.error}</p>}
        <details className="mt-3 text-xs muted">
          <summary className="cursor-pointer">Log</summary>
          <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap font-mono text-[10px]">{job.log.slice(-25).join("\n")}</pre>
        </details>
        <p className="mt-3 text-[11px] muted">Local models take a few minutes for an hour of content. You can keep exploring other graphs meanwhile.</p>
      </div>
    </div>
  );
}
