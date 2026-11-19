"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import type { ModelSettings, Probe, SettingsResponse } from "@/lib/types";
import Modal from "./Modal";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";

const PRESETS: Record<string, { base: string; model: string; hint: string }> = {
  ollama: { base: "http://localhost:11434", model: "qwen2.5:7b", hint: "ollama pull qwen2.5:7b && ollama pull nomic-embed-text" },
  lmstudio: { base: "http://localhost:1234/v1", model: "qwen2.5-7b-instruct", hint: "Start the LM Studio local server and load a model." },
  vllm: { base: "http://localhost:8000/v1", model: "Qwen/Qwen2.5-7B-Instruct", hint: "vllm serve <model> --port 8000" },
  openai: { base: "https://api.openai.com/v1", model: "gpt-4o-mini", hint: "Hosted OpenAI API — paste your API key below." },
  anthropic: { base: "", model: "claude-haiku-5-5", hint: "Hosted Claude API — paste your Anthropic API key below. Base URL is not needed." },
  gemini: { base: "", model: "gemini-2.5-flash", hint: "Google Gemini API — paste your API key below. Base URL is not needed." },
  groq: { base: "", model: "llama-3.3-70b-versatile", hint: "Groq API — paste your API key below. Base URL is not needed." },
  openrouter: { base: "", model: "openai/gpt-4o-mini", hint: "OpenRouter — paste your key; use any model id from openrouter.ai/models." },
  openai_compatible: { base: "http://localhost:8080/v1", model: "default", hint: "Any OpenAI-compatible endpoint (llama.cpp server, Groq, OpenRouter, …)." },
  mock: { base: "", model: "mock", hint: "No model at all — deterministic heuristics for trying the UI." },
};

export default function SettingsModal() {
  const { settingsOpen, setSettingsOpen, notify } = useStore();
  const [meta, setMeta] = useState<SettingsResponse | null>(null);
  const [form, setForm] = useState<ModelSettings | null>(null);
  const [probe, setProbe] = useState<{ llm: Probe; embeddings: Probe; whisper: Probe } | null>(null);
  const [busy, setBusy] = useState<"test" | "save" | null>(null);

  useEffect(() => {
    if (!settingsOpen) return;
    api.getSettings().then((s) => { setMeta(s); setForm(s.settings); setProbe(null); }).catch((e) => notify("error", (e as Error).message));
  }, [settingsOpen, notify]);

  if (!form || !meta) return <Modal open={settingsOpen} onClose={() => setSettingsOpen(false)} title="Model settings"><div className="muted text-sm">Loading…</div></Modal>;

  const set = <K extends keyof ModelSettings>(k: K, v: ModelSettings[K]) => setForm({ ...form, [k]: v });
  const setProvider = (p: string) => {
    const preset = PRESETS[p];
    setForm({ ...form, llm_provider: p, llm_base_url: preset?.base ?? form.llm_base_url, llm_model: preset?.model ?? form.llm_model });
  };

  const test = async () => {
    setBusy("test");
    try { setProbe(await api.testSettings(form)); } catch (e) { notify("error", (e as Error).message); } finally { setBusy(null); }
  };
  const save = async () => {
    setBusy("save");
    try { await api.saveSettings(form); notify("success", "Settings saved."); setSettingsOpen(false); }
    catch (e) { notify("error", (e as Error).message); } finally { setBusy(null); }
  };

  return (
    <Modal open={settingsOpen} onClose={() => setSettingsOpen(false)} title="Model settings" width="max-w-2xl">
      <Section title="Language model">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Provider">
            <select className="input" value={form.llm_provider} onChange={(e) => setProvider(e.target.value)}>
              {meta.providers.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </Field>
          <Field label="Model"><input className="input" value={form.llm_model} onChange={(e) => set("llm_model", e.target.value)} /></Field>
          <Field label="Base URL"><input className="input" value={form.llm_base_url} onChange={(e) => set("llm_base_url", e.target.value)} /></Field>
          <Field label="API key (optional)"><input className="input" type="password" value={form.llm_api_key} onChange={(e) => set("llm_api_key", e.target.value)} placeholder="only for hosted endpoints" /></Field>
          <Field label="Structured output mode">
            <select className="input" value={form.llm_structured_mode} onChange={(e) => set("llm_structured_mode", e.target.value)}>
              <option value="json">json (best for small local models)</option><option value="tools">tools (function calling)</option><option value="md_json">md_json</option>
            </select>
          </Field>
          <Field label="Context window (Ollama num_ctx)"><input className="input" type="number" value={form.llm_num_ctx} onChange={(e) => set("llm_num_ctx", Number(e.target.value))} /></Field>
        </div>
        <p className="mt-2 text-xs muted">{PRESETS[form.llm_provider]?.hint}</p>
      </Section>

      <Section title="Embeddings (node merging)">
        <div className="grid grid-cols-3 gap-3">
          <Field label="Provider">
            <select className="input" value={form.embedding_provider} onChange={(e) => set("embedding_provider", e.target.value)}>
              {meta.embedding_providers.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </Field>
          <Field label="Model"><input className="input" value={form.embedding_model} onChange={(e) => set("embedding_model", e.target.value)} /></Field>
          <Field label={`Merge threshold (${form.merge_threshold})`}>
            <input type="range" min={0.7} max={0.98} step={0.01} value={form.merge_threshold} onChange={(e) => set("merge_threshold", Number(e.target.value))} className="w-full accent-blue-500" />
          </Field>
          <Field label="Base URL" className="col-span-2"><input className="input" value={form.embedding_base_url} onChange={(e) => set("embedding_base_url", e.target.value)} /></Field>
        </div>
      </Section>

      <Section title="Speech-to-text (used only without captions)">
        <div className="grid grid-cols-4 gap-3">
          <Field label="Backend">
            <select className="input" value={form.whisper_backend} onChange={(e) => set("whisper_backend", e.target.value)}>
              {meta.whisper_backends.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </Field>
          <Field label="Model size"><input className="input" value={form.whisper_model} onChange={(e) => set("whisper_model", e.target.value)} /></Field>
          <Field label="Device">
            <select className="input" value={form.whisper_device} onChange={(e) => set("whisper_device", e.target.value)}><option>auto</option><option>cuda</option><option>cpu</option></select>
          </Field>
          <Field label="Compute">
            <select className="input" value={form.whisper_compute_type} onChange={(e) => set("whisper_compute_type", e.target.value)}><option>auto</option><option>int8</option><option>float16</option><option>float32</option></select>
          </Field>
        </div>
      </Section>

      <Section title="Chunking">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Window (minutes)"><input className="input" type="number" min={1} max={15} value={form.chunk_minutes} onChange={(e) => set("chunk_minutes", Number(e.target.value))} /></Field>
          <Field label="Overlap (seconds)"><input className="input" type="number" min={0} max={300} value={form.chunk_overlap_seconds} onChange={(e) => set("chunk_overlap_seconds", Number(e.target.value))} /></Field>
        </div>
      </Section>

      {probe && (
        <div className="mb-4 rounded-lg border p-3 text-xs" style={{ borderColor: "var(--border)" }}>
          <ProbeRow name="LLM" p={probe.llm} />
          <ProbeRow name="Embeddings" p={probe.embeddings} />
          <ProbeRow name="Whisper" p={{ reachable: !!probe.whisper.resolved, detail: probe.whisper.resolved ? `${probe.whisper.resolved} (${probe.whisper.model})` : "no backend installed — captions/subtitles only" }} />
          {probe.llm.available_models && probe.llm.available_models.length > 0 && <div className="mt-1 muted">Available: {probe.llm.available_models.slice(0, 12).join(", ")}</div>}
        </div>
      )}

      <div className="flex justify-end gap-2">
        <button className="btn" onClick={test} disabled={!!busy}>{busy === "test" ? <Loader2 size={14} className="animate-spin" /> : null} Test connection</button>
        <button className="btn btn-primary" onClick={save} disabled={!!busy}>{busy === "save" ? <Loader2 size={14} className="animate-spin" /> : null} Save</button>
      </div>
    </Modal>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="mb-4"><h3 className="mb-2 text-sm font-semibold">{title}</h3>{children}</section>;
}
function Field({ label, children, className = "" }: { label: string; children: React.ReactNode; className?: string }) {
  return <div className={className}><label className="label">{label}</label>{children}</div>;
}
function ProbeRow({ name, p }: { name: string; p: Probe }) {
  return (
    <div className="flex items-center gap-2 py-0.5">
      {p.reachable ? <CheckCircle2 size={14} className="text-emerald-500" /> : <XCircle size={14} className="text-red-500" />}
      <span className="w-24 font-semibold">{name}</span><span className="muted">{p.detail}</span>
    </div>
  );
}
