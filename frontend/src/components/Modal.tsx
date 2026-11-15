"use client";
import { X } from "lucide-react";
import { useEffect } from "react";

export default function Modal({ open, onClose, title, children, width = "max-w-xl" }: {
  open: boolean; onClose: () => void; title: string; children: React.ReactNode; width?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm" onMouseDown={onClose}>
      <div className={`panel w-full ${width} max-h-[90vh] overflow-auto rounded-2xl border shadow-2xl animate-fadeIn`} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b px-5 py-3" style={{ borderColor: "var(--border)" }}>
          <h2 className="text-base font-semibold">{title}</h2>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
}
