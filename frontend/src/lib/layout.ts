import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";

export const NODE_W = 210;
export const NODE_H = 64;

/** Left-to-right dagre layout. Prerequisites naturally land on the left, core topics on the right. */
export function layoutGraph<N extends Node, E extends Edge>(nodes: N[], edges: E[], direction: "LR" | "TB" = "LR"): N[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 36, ranksep: 110, marginx: 40, marginy: 40 });
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  const ids = new Set(nodes.map((n) => n.id));
  edges.forEach((e) => { if (ids.has(e.source) && ids.has(e.target)) g.setEdge(e.source, e.target); });
  dagre.layout(g);
  return nodes.map((n) => {
    const p = g.node(n.id);
    return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } };
  });
}
