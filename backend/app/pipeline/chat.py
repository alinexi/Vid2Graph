"""Graph-RAG chat: answer questions strictly from the transcript chunks linked to
the selected nodes (1-3). No vector search needed — the graph *is* the index."""
from __future__ import annotations

import re

from app.core.llm import LLMClient
from app.models.schemas import ChatRequest, ChatResponse, Citation, Graph, Node
from app.pipeline.chunker import fmt_ts, parse_ts

_CITE = re.compile(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]")

SYSTEM = """You are Vid2Graph's study assistant. Answer the user's question using ONLY the
transcript excerpts provided. Every excerpt line starts with a [mm:ss] timestamp.
- Cite timestamps inline like [14:15] whenever you reference what the speaker said.
- If the excerpts do not contain the answer, say so plainly and suggest what the speaker DID say.
- Be concise: 2-6 sentences, or a short list. Do not invent facts beyond the excerpts."""


def _chunks_for_nodes(graph: Graph, nodes: list[Node], max_chars: int = 7000) -> list[str]:
    chunk_ids: list[str] = []
    for n in nodes:
        ids = list(n.chunk_ids)
        if not ids:  # purple prerequisite: use chunks of the concepts it was inferred for
            for parent_id in n.inferred_from:
                parent = graph.node_by_id(parent_id)
                if parent:
                    ids.extend(parent.chunk_ids)
        for cid in ids:
            if cid not in chunk_ids:
                chunk_ids.append(cid)
    chunks = [c for c in graph.chunks if c.id in chunk_ids]
    chunks.sort(key=lambda c: c.start)
    texts: list[str] = []
    budget = max_chars
    per_chunk = max(1200, max_chars // max(1, len(chunks)))
    for c in chunks:
        t = _focus(c.text, nodes, per_chunk)
        if budget - len(t) < 0:
            break
        texts.append(t)
        budget -= len(t)
    return texts


def _focus(text: str, nodes: list[Node], limit: int) -> str:
    """Trim a chunk around lines mentioning the selected concepts."""
    if len(text) <= limit:
        return text
    lines = text.split("\n")
    keys = [k.lower() for n in nodes for k in [n.label, *n.aliases]]
    hits = [i for i, l in enumerate(lines) if any(k in l.lower() for k in keys)]
    if not hits:
        return text[:limit]
    keep: set[int] = set()
    for i in hits:
        keep.update(range(max(0, i - 3), min(len(lines), i + 4)))
    out = "\n".join(lines[i] for i in sorted(keep))
    return out[:limit]


def answer(llm: LLMClient, graph: Graph, req: ChatRequest) -> ChatResponse:
    nodes = [n for n in (graph.node_by_id(i) for i in req.node_ids) if n]
    if not nodes:
        raise ValueError("No valid nodes selected")
    excerpts = _chunks_for_nodes(graph, nodes)
    concept_block = "\n".join(
        f"- {n.label} [{n.layer}] — {n.eli5 or n.summary}" for n in nodes)
    if excerpts:
        context = "\n\n---\n\n".join(excerpts)
    else:
        context = "(no transcript excerpts are linked to these concepts — they were inferred as prerequisites)"
    user = (f"Selected concepts:\n{concept_block}\n\nTranscript excerpts:\n{context}\n\n"
            f"Question: {req.question}")
    history = [m.model_dump() for m in req.history[-6:]]
    text = llm.complete(SYSTEM, user, history=history)
    citations: list[Citation] = []
    seen: set[float] = set()
    for m in _CITE.finditer(text):
        sec = parse_ts(m.group(1))
        if sec is None or sec in seen:
            continue
        seen.add(sec)
        seg = next((s for s in graph.transcript if s.start <= sec <= s.end + 1), None)
        citations.append(Citation(start=sec, text=(seg.text if seg else fmt_ts(sec))[:200]))
    return ChatResponse(answer=text, citations=citations, context_chunks=excerpts)
