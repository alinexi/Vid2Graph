"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ReactFlowProvider } from "@xyflow/react";
import { api, ApiError } from "@/lib/api";
import { useStore } from "@/lib/store";
import type { Job } from "@/lib/types";
import Header from "./Header";
import VideoPlayer from "./VideoPlayer";
import TranscriptPanel from "./TranscriptPanel";
import FilterBar from "./FilterBar";
import GraphCanvas from "./GraphCanvas";
import NodeDrawer from "./NodeDrawer";
import GraphChat from "./GraphChat";
import IngestModal from "./IngestModal";
import SettingsModal from "./SettingsModal";
import JobProgress from "./JobProgress";
import Toast from "./Toast";

export default function Workspace() {
  const params = useSearchParams();
  const { graph, setGraph, setGraphs, setLoadingGraph, setError, notify, seekTo, theme, setTheme } = useStore();
  const [activeJob, setActiveJob] = useState<{ jobId: string; graphId: string } | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [leftWidth, setLeftWidth] = useState(40);
  const dragging = useRef(false);
  const booted = useRef(false);

  // theme bootstrap (mirrors the pre-hydration script)
  useEffect(() => {
    const t = (typeof window !== "undefined" && localStorage.getItem("v2g-theme")) as "dark" | "light" | null;
    const initial = t ?? (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    setTheme(initial);
  }, [setTheme]);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try { localStorage.setItem("v2g-theme", theme); } catch { /* ignore */ }
  }, [theme]);

  const loadGraph = useCallback(async (id: string, seekTime?: number) => {
    setLoadingGraph(true);
    setError(null);
    try {
      const g = await api.getGraph(id);
      setGraph(g);
      if (seekTime !== undefined && !Number.isNaN(seekTime)) setTimeout(() => seekTo(seekTime), 300);
      const url = new URL(window.location.href);
      url.searchParams.set("graph", id);
      url.searchParams.delete("t");
      window.history.replaceState(null, "", url.toString());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoadingGraph(false);
    }
  }, [setGraph, setLoadingGraph, setError, seekTo]);

  const refreshList = useCallback(async () => {
    try {
      const list = await api.listGraphs();
      setGraphs(list);
      return list;
    } catch (e) {
      setError((e as Error).message);
      return [];
    }
  }, [setGraphs, setError]);

  // first boot: list graphs, open ?graph= or the demo
  useEffect(() => {
    if (booted.current) return;
    booted.current = true;
    (async () => {
      const list = await refreshList();
      const wanted = params.get("graph");
      const t = params.get("t");
      const pick = (wanted && list.find((g) => g.id === wanted)?.id) || list.find((g) => g.is_demo)?.id || list[0]?.id;
      if (pick) await loadGraph(pick, t ? Number(t) : undefined);
    })();
  }, [params, refreshList, loadGraph]);

  // job polling
  useEffect(() => {
    if (!activeJob) return;
    let stop = false;
    const tick = async () => {
      try {
        const j = await api.getJob(activeJob.jobId);
        if (stop) return;
        setJob(j);
        if (j.status === "done") {
          notify("success", `Graph ready: ${j.message}`);
          await refreshList();
          await loadGraph(activeJob.graphId);
          setActiveJob(null);
          return;
        }
        if (j.status === "failed") {
          notify("error", j.error || "Processing failed");
          await refreshList();
          setActiveJob(null);
          return;
        }
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 0)) { setActiveJob(null); notify("error", (e as Error).message); return; }
      }
      if (!stop) setTimeout(tick, 1200);
    };
    tick();
    return () => { stop = true; };
  }, [activeJob, loadGraph, notify, refreshList]);

  // split-pane drag
  useEffect(() => {
    const move = (e: MouseEvent) => {
      if (!dragging.current) return;
      const pct = (e.clientX / window.innerWidth) * 100;
      setLeftWidth(Math.min(60, Math.max(24, pct)));
    };
    const up = () => { dragging.current = false; document.body.style.cursor = ""; };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
  }, []);

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <Header onSelectGraph={(id) => loadGraph(id)} onRefresh={refreshList} />
      <div className="flex min-h-0 flex-1">
        {/* Left: player + transcript */}
        <aside className="panel flex min-h-0 flex-col border-r" style={{ width: `${leftWidth}%` }}>
          <VideoPlayer />
          <TranscriptPanel />
        </aside>
        <div
          className="w-1 cursor-col-resize bg-transparent hover:bg-blue-500/40"
          onMouseDown={() => { dragging.current = true; document.body.style.cursor = "col-resize"; }}
          title="Drag to resize"
        />
        {/* Right: graph workspace */}
        <main className="relative flex min-h-0 min-w-0 flex-1 flex-col">
          <FilterBar onDeleted={async () => { const l = await refreshList(); const next = l[0]?.id; if (next) loadGraph(next); else setGraph(null); }} />
          <div className="relative min-h-0 flex-1">
            <ReactFlowProvider>
              <GraphCanvas />
            </ReactFlowProvider>
            <NodeDrawer />
            <GraphChat />
            {activeJob && job && <JobProgress job={job} onDismiss={() => setActiveJob(null)} />}
            {!graph && !activeJob && <EmptyState />}
          </div>
        </main>
      </div>
      <IngestModal onStarted={(j) => { setJob(null); setActiveJob(j); }} />
      <SettingsModal />
      <Toast />
    </div>
  );
}

function EmptyState() {
  const { setIngestOpen, notify, setGraph, setGraphs } = useStore();
  const reset = async () => {
    try {
      const g = await api.resetDemo();
      setGraphs(await api.listGraphs());
      setGraph(g);
    } catch (e) { notify("error", (e as Error).message); }
  };
  return (
    <div className="absolute inset-0 flex items-center justify-center p-8">
      <div className="panel max-w-md rounded-2xl border p-8 text-center shadow-xl">
        <div className="mb-3 text-4xl">🔵🟠🟣</div>
        <h2 className="text-lg font-semibold">No graph loaded</h2>
        <p className="muted mt-2 text-sm">Paste a YouTube link, upload an audio/video file, or drop an .srt/.vtt subtitle file to build your first knowledge graph.</p>
        <div className="mt-5 flex justify-center gap-2">
          <button className="btn btn-primary" onClick={() => setIngestOpen(true)}>New graph</button>
          <button className="btn" onClick={reset}>Load demo graph</button>
        </div>
      </div>
    </div>
  );
}
