"use client";
import { useStore } from "@/lib/store";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";

export default function Toast() {
  const toast = useStore((s) => s.toast);
  if (!toast) return null;
  const Icon = toast.kind === "error" ? AlertTriangle : toast.kind === "success" ? CheckCircle2 : Info;
  const color = toast.kind === "error" ? "border-red-500/50 text-red-500" : toast.kind === "success" ? "border-emerald-500/50 text-emerald-500" : "border-blue-500/50 text-blue-500";
  return (
    <div className={`panel fixed bottom-4 left-1/2 z-[60] flex max-w-lg -translate-x-1/2 items-start gap-2 rounded-lg border px-3 py-2 text-sm shadow-xl animate-fadeIn ${color}`}>
      <Icon size={16} className="mt-0.5 shrink-0" />
      <span className="text-[color:var(--text)]">{toast.text}</span>
      <button className="ml-2 opacity-60 hover:opacity-100" onClick={() => useStore.setState({ toast: null })} aria-label="Dismiss"><X size={14} /></button>
    </div>
  );
}
