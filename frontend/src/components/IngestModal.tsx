"use client";
import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import Modal from "./Modal";
import { FileAudio, FileText, Loader2, Youtube } from "lucide-react";

type Tab = "youtube" | "media" | "subtitles";

export default function IngestModal({ onStarted }: { onStarted: (job: { jobId: string; graphId: string }) => void }) {
  const { ingestOpen, setIngestOpen, notify } = useStore();
  const [tab, setTab] = useState<Tab>("youtube");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [language, setLanguage] = useState("en");
  const [forceWhisper, setForceWhisper] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const close = () => { if (!busy) setIngestOpen(false); };

  const submit = async () => {
    const form = new FormData();
    if (tab === "youtube") {
      if (!/youtube\.com|youtu\.be/.test(url)) { notify("error", "Paste a YouTube URL."); return; }
      form.append("url", url.trim());
      form.append("force_whisper", String(forceWhisper));
    } else {
      if (!file) { notify("error", "Choose a file first."); return; }
      form.append("file", file, file.name);
    }
    if (title.trim()) form.append("title", title.trim());
    form.append("language", language);
    setBusy(true);
    try {
      const res = await api.ingest(form);
      onStarted({ jobId: res.job_id, graphId: res.graph_id });
      setIngestOpen(false);
      setUrl(""); setTitle(""); setFile(null);
      notify("info", "Processing started.");
    } catch (e) { notify("error", (e as Error).message); } finally { setBusy(false); }
  };

  const accept = tab === "media" ? ".mp3,.m4a,.wav,.ogg,.flac,.aac,.opus,.webm,.mp4,.mkv,.mov,.avi,.m4v" : ".srt,.vtt,.txt";

  return (
    <Modal open={ingestOpen} onClose={close} title="New knowledge graph">
      <div className="mb-4 grid grid-cols-3 gap-1 rounded-lg border p-1" style={{ borderColor: "var(--border)" }}>
        {([["youtube", "YouTube URL", Youtube], ["media", "Audio / video", FileAudio], ["subtitles", "Subtitles (.srt/.vtt)", FileText]] as const).map(([k, label, Icon]) => (
          <button key={k} onClick={() => { setTab(k); setFile(null); }} className={`flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-sm ${tab === k ? "bg-blue-600 text-white" : "hover:bg-slate-500/10"}`}>
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {tab === "youtube" ? (
        <div className="mb-3">
          <label className="label">YouTube URL</label>
          <input className="input" placeholder="https://www.youtube.com/watch?v=…" value={url} onChange={(e) => setUrl(e.target.value)} autoFocus />
          <p className="mt-1 text-xs muted">Captions are fetched first (instant, no GPU). Whisper only runs when the video has none.</p>
          <label className="mt-2 flex items-center gap-2 text-xs">
            <input type="checkbox" checked={forceWhisper} onChange={(e) => setForceWhisper(e.target.checked)} /> Ignore captions and transcribe locally with Whisper
          </label>
        </div>
      ) : (
        <div className="mb-3">
          <label className="label">{tab === "media" ? "Audio or video file" : "Subtitle file"}</label>
          <div
            className="flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed p-6 text-sm hover:bg-slate-500/5"
            style={{ borderColor: "var(--border)" }}
            onClick={() => fileInput.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) setFile(f); }}
          >
            <input ref={fileInput} type="file" accept={accept} className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            {file ? <span className="font-medium">{file.name} <span className="muted">({(file.size / 1048576).toFixed(1)} MB)</span></span> : <span className="muted">Drop a file here or click to browse</span>}
          </div>
          <p className="mt-1 text-xs muted">
            {tab === "media" ? "Transcribed locally with Whisper. Nothing leaves your machine." : "Zero-GPU path: parsed instantly. Plain .txt without timestamps gets estimated timing."}
          </p>
        </div>
      )}

      <div className="mb-3 grid grid-cols-3 gap-3">
        <div className="col-span-2">
          <label className="label">Title (optional)</label>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Auto-detected" />
        </div>
        <div>
          <label className="label">Language</label>
          <input className="input" value={language} onChange={(e) => setLanguage(e.target.value)} placeholder="en" />
        </div>
      </div>

      <div className="flex justify-end gap-2">
        <button className="btn" onClick={close} disabled={busy}>Cancel</button>
        <button className="btn btn-primary" onClick={submit} disabled={busy}>{busy && <Loader2 size={14} className="animate-spin" />} Build graph</button>
      </div>
    </Modal>
  );
}
