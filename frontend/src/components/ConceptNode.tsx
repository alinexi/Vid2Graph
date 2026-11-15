"use client";
import { memo } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { LAYER_META, type GraphNode } from "@/lib/types";
import { Sparkles } from "lucide-react";
import { NODE_H, NODE_W } from "@/lib/layout";

export type ConceptData = {
  node: GraphNode;
  active: boolean;        // currently being discussed (near playback time)
  selected: boolean;
  chatIndex: number;      // 1..3 when part of the chat selection, 0 otherwise
  fresh: boolean;         // just added by "Generate deeper prerequisites"
  dimmed: boolean;
  direction: "LR" | "TB";
};
export type ConceptFlowNode = Node<ConceptData, "concept">;

const DIFF_DOTS: Record<GraphNode["difficulty"], string> = { beginner: "●○○", intermediate: "●●○", advanced: "●●●" };

function ConceptNodeImpl({ data }: NodeProps<ConceptFlowNode>) {
  const { node, active, selected, chatIndex, fresh, dimmed, direction } = data;
  const meta = LAYER_META[node.layer];
  const prereq = node.layer === "prerequisite";
  const mentions = node.mentions.length;
  return (
    <div
      className={`panel relative flex items-center gap-2.5 rounded-xl border px-3 py-2 shadow-sm transition-all ${selected ? "shadow-glow" : ""} ${active ? "animate-pulseRing" : ""} ${dimmed ? "opacity-30" : ""}`}
      style={{
        width: NODE_W, minHeight: NODE_H,
        borderColor: selected || active ? meta.color : "var(--border)",
        borderStyle: prereq ? "dashed" : "solid",
        borderWidth: selected ? 2 : 1.5,
        background: fresh ? `${meta.color}22` : undefined,
      }}
      title={`${meta.label} · ${node.difficulty}${mentions ? ` · ${mentions} mention${mentions > 1 ? "s" : ""}` : ""}\nClick: inspect & jump · Shift+click: add to chat`}
    >
      <Handle type="target" position={direction === "LR" ? Position.Left : Position.Top} className="!h-2 !w-2 !border-0 !bg-slate-400/60" />
      <span className="h-8 w-1.5 shrink-0 rounded-full" style={{ background: meta.color }} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-semibold leading-tight">{node.label}</div>
        <div className="mt-0.5 flex items-center gap-1.5 text-[10px] muted">
          <span style={{ color: meta.color }}>{meta.label.split(" ")[0]}</span>
          <span title={node.difficulty} className="tracking-tighter">{DIFF_DOTS[node.difficulty]}</span>
          {mentions > 0 && <span className="font-mono">{mentions}×</span>}
          {node.expanded && <Sparkles size={10} className="text-purple-400" />}
          {node.aliases.length > 0 && <span title={`aka ${node.aliases.join(", ")}`}>⇄</span>}
        </div>
      </div>
      {chatIndex > 0 && (
        <span className="absolute -right-2 -top-2 flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500 text-[10px] font-bold text-white shadow">{chatIndex}</span>
      )}
      <Handle type="source" position={direction === "LR" ? Position.Right : Position.Bottom} className="!h-2 !w-2 !border-0 !bg-slate-400/60" />
    </div>
  );
}

export default memo(ConceptNodeImpl);
