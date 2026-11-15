"""Stage 4 — entity resolution: merge synonymous nodes into one.

Two passes: (1) cheap lexical normalisation + alias / acronym matching, (2) cosine
similarity over embeddings (default threshold 0.85, configurable). Merged nodes keep
every timestamp ("jump-pills") and alias, and edges are re-pointed + deduplicated.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable, Optional

from app.core import runtime_settings
from app.models.schemas import DIFFICULTY_RANK, LAYER_RANK, Edge, Node
from app.pipeline.embeddings import cosine, get_embedder

_PAREN = re.compile(r"\s*\(([^)]+)\)\s*")
_ACRONYM = re.compile(r"^[A-Z0-9][A-Z0-9\-]{1,9}s?$")


def normalize(label: str) -> str:
    s = label.lower().strip()
    s = s.replace("-", " ").replace("_", " ").replace("/", " ")
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    # cheap singularisation: "raft logs" → "raft log"; keep short acronyms like "aws"
    words = []
    for w in s.split():
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        words.append(w)
    return " ".join(words)


def split_aliases(label: str) -> tuple[str, list[str]]:
    """'Large Language Model (LLM)' → ('Large Language Model', ['LLM'])."""
    m = _PAREN.search(label)
    if not m:
        return label.strip(), []
    inner = m.group(1).strip()
    outer = _PAREN.sub(" ", label).strip()
    if _ACRONYM.match(inner) or len(inner) < len(outer):
        return outer, [inner]
    return inner, [outer]


class _UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, i: int) -> int:
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def _merge_group(group: list[Node]) -> Node:
    """Combine a group of synonymous nodes into the strongest representative."""
    group = sorted(group, key=lambda n: (LAYER_RANK[n.layer], -len(n.mentions), -len(n.label)))
    head = group[0].model_copy(deep=True)
    seen_labels = {normalize(head.label)}
    for other in group[1:]:
        for alias in [other.label, *other.aliases]:
            if normalize(alias) not in seen_labels and alias.strip():
                head.aliases.append(alias.strip())
                seen_labels.add(normalize(alias))
        head.mentions.extend(other.mentions)
        head.chunk_ids.extend(c for c in other.chunk_ids if c not in head.chunk_ids)
        head.inferred_from.extend(i for i in other.inferred_from if i not in head.inferred_from)
        if not head.eli5 and other.eli5:
            head.eli5 = other.eli5
        if not head.summary and other.summary:
            head.summary = other.summary
        if DIFFICULTY_RANK[other.difficulty] < DIFFICULTY_RANK[head.difficulty] and other.layer == head.layer:
            head.difficulty = other.difficulty
        head.expanded = head.expanded or other.expanded
    # dedupe mentions (same second)
    uniq: dict[int, object] = {}
    for m in sorted(head.mentions, key=lambda m: m.start):
        uniq.setdefault(int(m.start), m)
    head.mentions = list(uniq.values())  # type: ignore[arg-type]
    head.aliases = list(dict.fromkeys(head.aliases))
    return head


def resolve(nodes: list[Node], edges: list[Edge], threshold: Optional[float] = None,
            use_embeddings: bool = True) -> tuple[list[Node], list[Edge], dict[str, str]]:
    """Return merged nodes, remapped edges and an old-id → new-id map."""
    if not nodes:
        return [], [], {}
    threshold = threshold if threshold is not None else float(runtime_settings.get("merge_threshold"))

    # Pass 0: extract parenthesised aliases.
    for n in nodes:
        label, aliases = split_aliases(n.label)
        n.label = label
        for a in aliases:
            if a not in n.aliases:
                n.aliases.append(a)

    uf = _UnionFind(len(nodes))

    # Pass 1: lexical — identical normalised label or alias overlap.
    key_to_idx: dict[str, int] = {}
    for i, n in enumerate(nodes):
        for key in [normalize(n.label), *map(normalize, n.aliases)]:
            if not key:
                continue
            if key in key_to_idx:
                uf.union(i, key_to_idx[key])
            else:
                key_to_idx[key] = i
    # acronym ↔ expansion: "KV Cache" vs "KVC" style initials
    initials: dict[str, int] = {}
    for i, n in enumerate(nodes):
        words = normalize(n.label).split()
        if len(words) >= 2:
            ini = "".join(w[0] for w in words)
            initials.setdefault(ini, i)
    for i, n in enumerate(nodes):
        key = normalize(n.label).replace(" ", "")
        if len(key) <= 6 and key in initials and initials[key] != i:
            uf.union(i, initials[key])

    # Pass 2: embeddings.
    if use_embeddings and len(nodes) > 1:
        texts = [n.label for n in nodes]
        vecs = get_embedder().embed(texts)
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                if uf.find(i) == uf.find(j):
                    continue
                if cosine(vecs[i], vecs[j]) >= threshold:
                    uf.union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(nodes)):
        groups[uf.find(i)].append(i)

    id_map: dict[str, str] = {}
    merged: list[Node] = []
    for root, members in sorted(groups.items()):
        head = _merge_group([nodes[i] for i in members])
        for i in members:
            id_map[nodes[i].id] = head.id
        merged.append(head)

    # remap inferred_from
    for n in merged:
        n.inferred_from = list(dict.fromkeys(id_map.get(i, i) for i in n.inferred_from))

    return merged, remap_edges(edges, id_map), id_map


def remap_edges(edges: Iterable[Edge], id_map: dict[str, str]) -> list[Edge]:
    seen: set[tuple[str, str, str]] = set()
    out: list[Edge] = []
    for e in edges:
        s, t = id_map.get(e.source, e.source), id_map.get(e.target, e.target)
        if s == t:
            continue
        key = (s, t, e.relation)
        if key in seen or (t, s, e.relation) in seen and e.relation in ("compared_with", "contrasts_with", "related_to"):
            continue
        seen.add(key)
        out.append(Edge(id=e.id, source=s, target=t, relation=e.relation, label=e.label))
    return out


def merge_into_graph(existing_nodes: list[Node], existing_edges: list[Edge],
                     new_nodes: list[Node], new_edges: list[Edge]) -> tuple[list[Node], list[Edge], list[str], list[str]]:
    """Merge freshly generated nodes into an existing graph, returning the ids that are genuinely new."""
    before = {n.id for n in existing_nodes}
    nodes, edges, id_map = resolve(existing_nodes + new_nodes, existing_edges + new_edges)
    new_ids = [n.id for n in nodes if n.id not in before]
    new_edge_ids = [e.id for e in edges if e.id in {ne.id for ne in new_edges}]
    return nodes, edges, new_ids, new_edge_ids
