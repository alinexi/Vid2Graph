"""End-to-end pipeline with the mock LLM: chunks → pass 1 → resolve → pass 2 → edges."""
from app.core.llm import get_llm
from app.models.schemas import TranscriptSegment
from app.pipeline import graph_gen
from app.pipeline.chunker import chunk_transcript
from app.pipeline.resolver import resolve

TEXT = [
    "We ran into Split-Brain issues in production early on.",
    "So we had to migrate from Paxos to Raft to achieve reliable Consensus.",
    "Raft is easier to explain than Paxos, which matters for Leader Election.",
    "Our Fencing Tokens prevented stale leaders from writing.",
]


def test_mock_pipeline_produces_three_layers():
    segs = [TranscriptSegment(id=i, start=i * 30, end=i * 30 + 29, text=t) for i, t in enumerate(TEXT)]
    chunks = chunk_transcript(segs)
    llm = get_llm()
    raw = graph_gen.pass1_extract(llm, chunks, progress=lambda *_: None)
    assert any(n.label == "Split-Brain" for n in raw)
    assert all(n.mentions and n.mentions[0].chunk_id == "c0" for n in raw)
    nodes, edges, _ = resolve(raw, [])
    graph_gen.pass2_enrich(llm, nodes, progress=lambda *_: None)
    assert all(n.eli5 for n in nodes)
    prereqs, rel_edges = graph_gen.pass2_synthesize(llm, nodes, progress=lambda *_: None)
    edges = rel_edges + graph_gen.prerequisite_edges(prereqs)
    nodes, edges, _ = resolve(nodes + prereqs, edges)
    layers = {n.layer for n in nodes}
    assert layers == {"core", "jargon", "prerequisite"}
    ids = {n.id for n in nodes}
    assert all(e.source in ids and e.target in ids for e in edges)
    assert any(e.relation == "prerequisite_for" for e in edges)


def test_expand_node_adds_prerequisites():
    from app.models.schemas import Node
    llm = get_llm()
    node = Node(id="x", label="Raft", layer="core", eli5="consensus")
    new = graph_gen.expand_node(llm, node, [node])
    assert len(new) == 2 and all(n.layer == "prerequisite" and n.inferred_from == ["x"] for n in new)
