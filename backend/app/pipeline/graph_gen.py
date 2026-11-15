"""Stage 3 — two-pass structured extraction tuned for small local models.

Pass 1 (per chunk, parallelisable): find *Core Concepts* (explained) and *Dropped
Jargon* (mentioned, not explained) with the ``[mm:ss]`` marker where each appears.

Pass 2 (over the deduplicated concept *list* only — a tiny token footprint):
  2a. difficulty + ELI5 primer + one-line summary for every concept (batched)
  2b. implicit *Prerequisites* never named in the video + directed relations (batched)

Everything is Pydantic-validated via Instructor; the prompts deliberately ask for
small, flat JSON so 7B models succeed.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Literal, Optional

from pydantic import BaseModel, Field

from app.core import runtime_settings
from app.core.llm import LLMClient, LLMError
from app.models.schemas import Chunk, Difficulty, Edge, Mention, Node, RelationType
from app.pipeline.chunker import fmt_ts, parse_ts

log = logging.getLogger("vid2graph.graph_gen")
Progress = Callable[[str, float], None]


# ── Pass 1 schema ────────────────────────────────────────────────────────────
class ExtractedConcept(BaseModel):
    name: str = Field(description="Canonical short name of the concept, 1-5 words, Title Case")
    layer: Literal["core", "jargon"] = Field(
        description="core = the speaker explains or discusses it; jargon = name-dropped without explanation")
    timestamp: str = Field(description="The [mm:ss] marker right before the mention, e.g. '14:15'")
    context_snippet: str = Field(description="Verbatim 10-30 word quote containing the mention")
    what_was_said: str = Field(default="", description="One sentence: what the speaker said about it")


class ChunkExtraction(BaseModel):
    concepts: list[ExtractedConcept] = Field(default_factory=list)


# ── Pass 2 schemas ───────────────────────────────────────────────────────────
class ConceptEnrichment(BaseModel):
    name: str
    difficulty: Difficulty = Field(description="beginner | intermediate | advanced for a software engineer")
    eli5: str = Field(description="2-3 sentence plain-language primer a newcomer would understand")
    summary: str = Field(default="", description="One sentence on how it was used in this talk")


class EnrichmentBatch(BaseModel):
    concepts: list[ConceptEnrichment] = Field(default_factory=list)


class Prerequisite(BaseModel):
    name: str = Field(description="Foundational concept NOT named in the video, Title Case")
    eli5: str = Field(description="2 sentence plain-language primer")
    difficulty: Difficulty = "beginner"
    prerequisite_for: list[str] = Field(description="Names (from the provided list) that need this first")


class Relation(BaseModel):
    source: str
    target: str
    relation: RelationType = "related_to"


class SynthesisBatch(BaseModel):
    prerequisites: list[Prerequisite] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)


class ExpansionResult(BaseModel):
    prerequisites: list[Prerequisite] = Field(default_factory=list)


class GraphTitle(BaseModel):
    title: str
    summary: str = Field(description="2-3 sentence overview of what the video teaches")


# ── Prompts ──────────────────────────────────────────────────────────────────
PASS1_SYSTEM = """You are an expert technical editor building a knowledge graph from a transcript.
The transcript lines start with a [mm:ss] timestamp marker.

Extract every technical concept, tool, algorithm, system, or named phenomenon and classify it:
- "core": the speaker EXPLAINS, analyses, or spends time discussing it.
- "jargon": the speaker name-drops it in passing WITHOUT defining it (assumes the listener knows).

Rules:
- Use the canonical name in Title Case (e.g. "Raft", "Split-Brain", "KV-Cache").
- Prefer the common acronym AND spelled-out form only as one name, e.g. "Large Language Model (LLM)".
- Skip generic words (team, product, company, people, thing).
- timestamp must be copied from the nearest preceding [mm:ss] marker.
- 3 to 12 concepts per chunk. Quality over quantity."""

PASS2A_SYSTEM = """You are a patient senior engineer writing primers for learners.
For each concept give its difficulty for a working software engineer and a 2-3 sentence
ELI5 (explain-like-I'm-five) primer that uses an analogy where helpful. Keep names EXACTLY as given."""

PASS2B_SYSTEM = """You are a curriculum designer mapping prerequisite knowledge.
You receive concepts discussed in a video. Do two things:
1. prerequisites: list foundational concepts a learner MUST already understand to follow these,
   that are NOT already in the list (they were never named in the video). 2-8 items. Each lists
   which given concepts it is a prerequisite for. Use EXACT names from the list.
2. relations: directed edges BETWEEN the given concepts using relation types:
   prerequisite_for, compared_with, part_of, uses, leads_to, contrasts_with, example_of, related_to.
   Only add an edge when it is clearly supported. Use EXACT names from the list."""

EXPAND_SYSTEM = """You are a curriculum designer. Given one concept, list 2-5 deeper foundational
prerequisites a learner must understand first. Exclude anything in the 'already in graph' list.
Each prerequisite: Title Case name, 2-sentence ELI5, difficulty, and prerequisite_for=[the concept]."""

TITLE_SYSTEM = "Given concept names from a video transcript, write a concise descriptive title (max 10 words) and a short summary."


# ── Pipeline ─────────────────────────────────────────────────────────────────
def _batched(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def extract_chunk(llm: LLMClient, chunk: Chunk) -> list[Node]:
    user = (f"Transcript chunk {chunk.index + 1} ({fmt_ts(chunk.start)} – {fmt_ts(chunk.end)}):\n\n{chunk.text}")
    result = llm.structured(ChunkExtraction, PASS1_SYSTEM, user)
    nodes: list[Node] = []
    for c in result.concepts:
        name = c.name.strip().strip('"').strip()
        if len(name) < 2 or len(name) > 80:
            continue
        ts = parse_ts(c.timestamp)
        if ts is None or ts < chunk.start - 5 or ts > chunk.end + 5:
            ts = chunk.start
        nodes.append(Node(
            label=name, layer=c.layer,
            summary=c.what_was_said.strip(),
            mentions=[Mention(start=ts, snippet=c.context_snippet.strip()[:300], chunk_id=chunk.id)],
            chunk_ids=[chunk.id],
        ))
    return nodes


def pass1_extract(llm: LLMClient, chunks: list[Chunk], progress: Progress) -> list[Node]:
    nodes: list[Node] = []
    workers = max(1, int(runtime_settings.get("max_chunks_parallel") if hasattr(runtime_settings, "get") else 2))
    workers = min(workers, len(chunks)) or 1
    done = 0
    failures = 0

    def run(ch: Chunk) -> list[Node]:
        try:
            return extract_chunk(llm, ch)
        except LLMError as exc:
            log.warning("chunk %s failed: %s", ch.id, exc)
            return []

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(run, chunks):
            done += 1
            if not res:
                failures += 1
            nodes.extend(res)
            progress(f"Pass 1: extracted concepts from chunk {done}/{len(chunks)} ({len(nodes)} so far)",
                     0.35 + 0.3 * done / len(chunks))
    if failures == len(chunks):
        raise LLMError("The model failed to extract concepts from every chunk. "
                       "Check the model settings (is the model pulled and the endpoint reachable?).")
    return nodes


def _name_list(nodes: list[Node]) -> str:
    return "\n".join(f"- {n.label} ({n.layer})" for n in nodes)


def pass2_enrich(llm: LLMClient, nodes: list[Node], progress: Progress) -> None:
    batches = _batched(nodes, 20)
    for bi, batch in enumerate(batches):
        user = "Concepts:\n" + "\n".join(
            f"- {n.label} — context: \"{(n.mentions[0].snippet if n.mentions else n.summary)[:160]}\"" for n in batch)
        try:
            res = llm.structured(EnrichmentBatch, PASS2A_SYSTEM, user)
        except LLMError as exc:
            log.warning("enrichment batch %d failed: %s", bi, exc)
            continue
        by_name = {_norm(c.name): c for c in res.concepts}
        for n in batch:
            c = by_name.get(_norm(n.label))
            if c:
                n.difficulty = c.difficulty
                n.eli5 = c.eli5.strip()
                if c.summary and not n.summary:
                    n.summary = c.summary.strip()
        progress(f"Pass 2a: primers & difficulty {bi + 1}/{len(batches)}", 0.68 + 0.1 * (bi + 1) / len(batches))


def pass2_synthesize(llm: LLMClient, nodes: list[Node], progress: Progress) -> tuple[list[Node], list[Edge]]:
    """Infer purple prerequisite nodes + relation edges from the concept list."""
    new_nodes: list[Node] = []
    edges: list[Edge] = []
    batches = _batched(nodes, 40)
    for bi, batch in enumerate(batches):
        user = "Concepts discussed in the video:\n" + _name_list(batch)
        try:
            res = llm.structured(SynthesisBatch, PASS2B_SYSTEM, user)
        except LLMError as exc:
            log.warning("synthesis batch %d failed: %s", bi, exc)
            continue
        new_nodes.extend(_materialize_prereqs(res.prerequisites, batch))
        edges.extend(_materialize_relations(res.relations, batch))
        progress(f"Pass 2b: prerequisites & relations {bi + 1}/{len(batches)}", 0.78 + 0.1 * (bi + 1) / len(batches))
    return new_nodes, edges


def _materialize_prereqs(prereqs: list[Prerequisite], known: list[Node]) -> list[Node]:
    by_name = {_norm(n.label): n for n in known}
    out: list[Node] = []
    for p in prereqs:
        name = p.name.strip()
        if not name or _norm(name) in by_name:
            continue  # already explicitly mentioned → not an *implicit* prerequisite
        targets = [by_name[_norm(t)].id for t in p.prerequisite_for if _norm(t) in by_name]
        out.append(Node(label=name, layer="prerequisite", difficulty=p.difficulty, eli5=p.eli5.strip(),
                        inferred_from=targets))
    return out


def _materialize_relations(rels: list[Relation], known: list[Node]) -> list[Edge]:
    by_name = {_norm(n.label): n for n in known}
    out: list[Edge] = []
    for r in rels:
        s, t = by_name.get(_norm(r.source)), by_name.get(_norm(r.target))
        if not s or not t or s.id == t.id:
            continue
        out.append(Edge(source=s.id, target=t.id, relation=r.relation))
    return out


def prerequisite_edges(prereq_nodes: list[Node]) -> list[Edge]:
    return [Edge(source=p.id, target=t, relation="prerequisite_for")
            for p in prereq_nodes for t in p.inferred_from]


def expand_node(llm: LLMClient, node: Node, all_nodes: list[Node]) -> list[Node]:
    neighbours = ", ".join(n.label for n in all_nodes if n.id != node.id)[:1500]
    user = (f"Concept: {node.label}\nLayer: {node.layer}\nPrimer: {node.eli5 or node.summary}\n"
            f"Already in graph (exclude these): {neighbours}")
    res = llm.structured(ExpansionResult, EXPAND_SYSTEM, user)
    out: list[Node] = []
    for p in res.prerequisites:
        if not p.name.strip():
            continue
        out.append(Node(label=p.name.strip(), layer="prerequisite", difficulty=p.difficulty,
                        eli5=p.eli5.strip(), inferred_from=[node.id]))
    return out


def generate_title(llm: LLMClient, nodes: list[Node], fallback: str) -> tuple[str, str]:
    try:
        res = llm.structured(GraphTitle, TITLE_SYSTEM,
                             "Concepts: " + ", ".join(n.label for n in nodes[:40]))
        return (res.title.strip() or fallback), res.summary.strip()
    except LLMError:
        return fallback, ""


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("-", " ").replace("_", " ").split())
