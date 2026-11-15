"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import { fmtTime } from "@/lib/utils";
import { Link2, Pause, Play, RotateCcw, RotateCw } from "lucide-react";

declare global {
  interface Window { YT?: any; onYouTubeIframeAPIReady?: () => void }
}

let ytApiPromise: Promise<void> | null = null;
function loadYouTubeApi(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.YT?.Player) return Promise.resolve();
  if (!ytApiPromise) {
    ytApiPromise = new Promise((resolve) => {
      const prev = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => { prev?.(); resolve(); };
      const s = document.createElement("script");
      s.src = "https://www.youtube.com/iframe_api";
      document.head.appendChild(s);
    });
  }
  return ytApiPromise;
}

export default function VideoPlayer() {
  const graph = useStore((s) => s.graph);
  if (!graph) return <div className="panel flex aspect-video items-center justify-center border-b text-sm muted">No media</div>;
  if (graph.media_kind === "youtube" && graph.media_url) return <YouTubePlayer key={graph.id} videoId={graph.media_url} />;
  if ((graph.media_kind === "video" || graph.media_kind === "audio") && graph.media_url)
    return <HtmlMediaPlayer key={graph.id} src={api.mediaUrl(graph.media_url)} kind={graph.media_kind} />;
  return <VirtualPlayer key={graph.id} />;
}

/* ── YouTube ─────────────────────────────────────────────────────────────── */
function YouTubePlayer({ videoId }: { videoId: string }) {
  const host = useRef<HTMLDivElement>(null);
  const player = useRef<any>(null);
  const seek = useStore((s) => s.seek);
  const { setCurrentTime, setPlaying } = useStore();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let poll: ReturnType<typeof setInterval> | undefined;
    loadYouTubeApi().then(() => {
      if (cancelled || !host.current) return;
      player.current = new window.YT.Player(host.current, {
        videoId, width: "100%", height: "100%",
        playerVars: { rel: 0, modestbranding: 1, playsinline: 1 },
        events: {
          onReady: () => {
            setReady(true);
            poll = setInterval(() => {
              const p = player.current;
              if (p?.getCurrentTime) setCurrentTime(p.getCurrentTime());
            }, 250);
          },
          onStateChange: (e: { data: number }) => setPlaying(e.data === 1),
        },
      });
    });
    return () => { cancelled = true; if (poll) clearInterval(poll); player.current?.destroy?.(); player.current = null; };
  }, [videoId, setCurrentTime, setPlaying]);

  useEffect(() => {
    if (!seek || !ready || !player.current?.seekTo) return;
    player.current.seekTo(seek.time, true);
    player.current.playVideo?.();
  }, [seek, ready]);

  return (
    <div className="aspect-video w-full shrink-0 bg-black">
      <div ref={host} className="h-full w-full" />
    </div>
  );
}

/* ── Local file ──────────────────────────────────────────────────────────── */
function HtmlMediaPlayer({ src, kind }: { src: string; kind: "video" | "audio" }) {
  const ref = useRef<HTMLVideoElement | HTMLAudioElement>(null);
  const seek = useStore((s) => s.seek);
  const { setCurrentTime, setPlaying } = useStore();

  useEffect(() => {
    if (!seek || !ref.current) return;
    ref.current.currentTime = seek.time;
    ref.current.play().catch(() => undefined);
  }, [seek]);

  const common = {
    ref: ref as never, src, controls: true, className: "w-full",
    onTimeUpdate: () => setCurrentTime(ref.current?.currentTime ?? 0),
    onPlay: () => setPlaying(true), onPause: () => setPlaying(false),
  };
  return (
    <div className={`w-full shrink-0 bg-black ${kind === "video" ? "aspect-video" : "p-3"}`}>
      {kind === "video" ? <video {...common} className="h-full w-full" /> : <audio {...common} />}
    </div>
  );
}

/* ── Transcript-only "virtual" player ───────────────────────────────────── */
function VirtualPlayer() {
  const { graph, currentTime, playing, setCurrentTime, setPlaying, seekTo, patchGraph, notify } = useStore();
  const seek = useStore((s) => s.seek);
  const raf = useRef<number>();
  const last = useRef<number>(0);
  const [attachUrl, setAttachUrl] = useState("");
  const [attaching, setAttaching] = useState(false);
  const duration = graph?.duration ?? 0;

  useEffect(() => { if (seek) setPlaying(true); }, [seek, setPlaying]);

  useEffect(() => {
    if (!playing) { if (raf.current) cancelAnimationFrame(raf.current); return; }
    last.current = performance.now();
    const step = (now: number) => {
      const dt = (now - last.current) / 1000;
      last.current = now;
      const t = useStore.getState().currentTime + dt;
      if (t >= duration) { setCurrentTime(duration); setPlaying(false); return; }
      setCurrentTime(t);
      raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => { if (raf.current) cancelAnimationFrame(raf.current); };
  }, [playing, duration, setCurrentTime, setPlaying]);

  const attach = useCallback(async () => {
    if (!graph || !attachUrl.trim()) return;
    setAttaching(true);
    try {
      const meta = await api.patchGraph(graph.id, { media_url: attachUrl.trim() });
      if (meta.media_kind !== "youtube") { notify("error", "Please paste a valid YouTube URL."); return; }
      patchGraph({ media_kind: meta.media_kind, media_url: meta.media_url, source_url: meta.source_url });
      notify("success", "YouTube video attached — timestamps now drive the player.");
    } catch (e) { notify("error", (e as Error).message); } finally { setAttaching(false); }
  }, [graph, attachUrl, patchGraph, notify]);

  const pct = duration ? (currentTime / duration) * 100 : 0;
  return (
    <div className="shrink-0 border-b p-4" style={{ borderColor: "var(--border)", background: "linear-gradient(135deg, rgba(168,85,247,.12), rgba(249,115,22,.10), rgba(59,130,246,.12))" }}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-wide muted">Transcript-only playback</div>
          <h2 className="truncate text-sm font-semibold" title={graph?.title}>{graph?.title}</h2>
          <p className="muted mt-0.5 text-xs">No media attached. The clock below drives transcript sync and node highlighting.</p>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <button className="btn" onClick={() => seekTo(Math.max(0, currentTime - 15))} title="Back 15s"><RotateCcw size={14} /></button>
        <button className="btn btn-primary h-9 w-9 justify-center" onClick={() => setPlaying(!playing)} title={playing ? "Pause" : "Play"}>
          {playing ? <Pause size={16} /> : <Play size={16} />}
        </button>
        <button className="btn" onClick={() => seekTo(Math.min(duration, currentTime + 15))} title="Forward 15s"><RotateCw size={14} /></button>
        <span className="font-mono text-xs tabular-nums">{fmtTime(currentTime)}</span>
        <input
          type="range" min={0} max={Math.max(1, duration)} step={0.5} value={currentTime}
          onChange={(e) => seekTo(Number(e.target.value))}
          className="h-1.5 flex-1 cursor-pointer accent-blue-500"
          style={{ background: `linear-gradient(90deg, #3b82f6 ${pct}%, rgba(148,163,184,.3) ${pct}%)` }}
          aria-label="Scrub"
        />
        <span className="font-mono text-xs muted tabular-nums">{fmtTime(duration)}</span>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <Link2 size={14} className="muted shrink-0" />
        <input className="input" placeholder="Attach a YouTube URL to play the real video…" value={attachUrl}
               onChange={(e) => setAttachUrl(e.target.value)} onKeyDown={(e) => e.key === "Enter" && attach()} />
        <button className="btn" disabled={attaching || !attachUrl.trim()} onClick={attach}>Attach</button>
      </div>
    </div>
  );
}
