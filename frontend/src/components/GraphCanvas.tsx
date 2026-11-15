"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background, BackgroundVariant, Controls, type Edge, MarkerType, MiniMap, type NodeMouseHandler, ReactFlow,
  useEdgesState, useNodesInitialized, useNodesState, useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useStore, nodeVisible } from "@/lib/store";
import { layoutGraph } from "@/lib/layout";
import { LAYER_META, RELATION_LABEL, type GraphEdge } from "@/lib/types";
import ConceptNode, { type ConceptFlowNode } from "./ConceptNode";

const nodeTypes = { concept: ConceptNode };

function edgeStyle(e: GraphEdge, dark: boolean) {
  const base = dark ? "#475569" : "#94a3b8";
  switch (e.relation) {
    case "prerequisite_for": return { stroke: "#a855f7", strokeDasharray: "6 4", animated: true };
    case "compared_with":
    case "contrasts_with": return { stroke: "#f97316", strokeDasharray: undefined, animated: false };
    case "leads_to": return { stroke: "#f97316", strokeDasharray: undefined, animated: true };
    case "part_of":
    case "uses":
    case "example_of": return { stroke: "#3b82f6", strokeDasharray: undefined, animated: false };
    default: return { stroke: base, strokeDasharray: "2 4", animated: false };
  }
}

export default function GraphCanvas() {
  const { graph, level, search, visibleLayers, selectedNodeId, chatSelection, currentTime, highlightedNodeIds, layoutDirection, theme, selectNode, toggleChatSelection, setHighlighted } = useStore();
  const { fitView } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState<ConceptFlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const positions = useRef<Map<string, { x: number; y: number }>>(new Map());
  const [layoutKey, setLayoutKey] = useState("");
  const pendingFit = useRef(false);
  const nodesInitialized = useNodesInitialized();

  const dark = theme === "dark";

  // visible node ids under the current filters
  const visibleIds = useMemo(() => {
    if (!graph) return new Set<string>();
    return new Set(graph.nodes.filter((n) => nodeVisible(n, level, search, visibleLayers)).map((n) => n.id));
  }, [graph, level, search, visibleLayers]);

  // "active now" = mentioned within ±20s of the playhead
  const activeIds = useMemo(() => {
    if (!graph) return new Set<string>();
    const s = new Set<string>();
    for (const n of graph.nodes) if (n.mentions.some((m) => Math.abs(m.start - currentTime) <= 20)) s.add(n.id);
    return s;
  }, [graph, currentTime]);

  // (re)layout when the visible set, direction or graph changes
  useEffect(() => {
    if (!graph) { setNodes([]); setEdges([]); return; }
    const vis = graph.nodes.filter((n) => visibleIds.has(n.id));
    const key = `${graph.id}:${layoutDirection}:${vis.map((n) => n.id).join(",")}`;
    const rfEdges: Edge[] = graph.edges
      .filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target))
      .map((e) => {
        const st = edgeStyle(e, dark);
        return {
          id: e.id, source: e.source, target: e.target, type: "smoothstep",
          label: RELATION_LABEL[e.relation], animated: st.animated,
          style: { stroke: st.stroke, strokeDasharray: st.strokeDasharray },
          markerEnd: { type: MarkerType.ArrowClosed, color: st.stroke, width: 16, height: 16 },
          labelStyle: { fontSize: 10, fill: dark ? "#94a3b8" : "#64748b" },
          labelBgStyle: { fill: dark ? "#0b1020" : "#f8fafc", fillOpacity: 0.9 },
          labelShowBg: true,
        };
      });
    let rfNodes: ConceptFlowNode[] = vis.map((n) => ({
      id: n.id, type: "concept", position: positions.current.get(n.id) ?? { x: 0, y: 0 },
      data: { node: n, active: false, selected: false, chatIndex: 0, fresh: false, dimmed: false, direction: layoutDirection },
    }));
    if (key !== layoutKey) {
      rfNodes = layoutGraph(rfNodes, rfEdges, layoutDirection);
      rfNodes.forEach((n) => positions.current.set(n.id, n.position));
      setLayoutKey(key);
      pendingFit.current = true;
    }
    setNodes(rfNodes);
    setEdges(rfEdges);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, visibleIds, layoutDirection, dark]);

  // fit the viewport once React Flow has measured the freshly laid-out nodes
  useEffect(() => {
    if (!nodesInitialized || !pendingFit.current) return;
    pendingFit.current = false;
    const t = setTimeout(() => fitView({ padding: 0.15, duration: 400 }), 50);
    return () => clearTimeout(t);
  }, [nodesInitialized, nodes, fitView]);

  // cheap per-frame data updates (selection, playhead highlight, chat badges)
  useEffect(() => {
    setNodes((prev) => prev.map((n) => {
      const fresh = highlightedNodeIds.includes(n.id);
      const selected = n.id === selectedNodeId;
      const chatIndex = chatSelection.indexOf(n.id) + 1;
      const active = activeIds.has(n.id);
      const dimmed = !!search.trim() ? false : false;
      if (n.data.fresh === fresh && n.data.selected === selected && n.data.chatIndex === chatIndex && n.data.active === active && n.data.dimmed === dimmed) return n;
      return { ...n, data: { ...n.data, fresh, selected, chatIndex, active, dimmed } };
    }));
  }, [selectedNodeId, chatSelection, activeIds, highlightedNodeIds, search, setNodes]);

  // clear "fresh" highlight after a while
  useEffect(() => {
    if (!highlightedNodeIds.length) return;
    const t = setTimeout(() => setHighlighted([]), 6000);
    return () => clearTimeout(t);
  }, [highlightedNodeIds, setHighlighted]);

  const onNodeClick: NodeMouseHandler<ConceptFlowNode> = useCallback((evt, n) => {
    if (evt.shiftKey || evt.metaKey || evt.ctrlKey) toggleChatSelection(n.id);
    else selectNode(n.id);
  }, [selectNode, toggleChatSelection]);

  const onNodeDragStop = useCallback((_: unknown, n: ConceptFlowNode) => { positions.current.set(n.id, n.position); }, []);

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes} edges={edges} nodeTypes={nodeTypes}
        onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick} onNodeDragStop={onNodeDragStop}
        onPaneClick={() => selectNode(null)}
        fitView minZoom={0.15} maxZoom={2} proOptions={{ hideAttribution: true }}
        nodesConnectable={false} deleteKeyCode={null} colorMode={dark ? "dark" : "light"}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} color={dark ? "#1e293b" : "#cbd5e1"} />
        <Controls showInteractive={false} position="bottom-right" />
        <MiniMap
          pannable zoomable position="top-right"
          nodeColor={(n) => LAYER_META[(n as ConceptFlowNode).data.node.layer].color}
          maskColor={dark ? "rgba(2,6,23,.6)" : "rgba(241,245,249,.7)"}
        />
      </ReactFlow>
      <Legend visible={visibleIds.size} total={graph?.nodes.length ?? 0} />
    </div>
  );
}

function Legend({ visible, total }: { visible: number; total: number }) {
  const { graph } = useStore();
  if (!graph) return null;
  return (
    <div className="panel pointer-events-none absolute bottom-3 left-3 rounded-lg border px-3 py-2 text-[11px] shadow">
      {(["core", "jargon", "prerequisite"] as const).map((l) => (
        <div key={l} className="flex items-center gap-2 py-0.5">
          <span className={`inline-block h-2.5 w-2.5 rounded-sm ${l === "prerequisite" ? "border border-dashed" : ""}`} style={{ background: l === "prerequisite" ? "transparent" : LAYER_META[l].color, borderColor: LAYER_META[l].color }} />
          <span>{LAYER_META[l].label}</span>
        </div>
      ))}
      <div className="mt-1 border-t pt-1 muted" style={{ borderColor: "var(--border)" }}>{visible}/{total} nodes shown · shift+click to chat</div>
    </div>
  );
}
