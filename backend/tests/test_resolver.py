from app.models.schemas import Edge, Mention, Node
from app.pipeline.resolver import normalize, resolve, split_aliases


def test_split_aliases():
    assert split_aliases("Large Language Model (LLM)") == ("Large Language Model", ["LLM"])
    assert split_aliases("Raft") == ("Raft", [])


def test_normalize():
    assert normalize("Split-Brain") == normalize("split brain")
    assert normalize("Raft Logs") == "raft log"


def test_lexical_merge_keeps_all_timestamps_and_remaps_edges():
    a = Node(id="a", label="LLM", layer="jargon", mentions=[Mention(start=615, snippet="LLM")], chunk_ids=["c1"])
    b = Node(id="b", label="Large Language Model (LLM)", layer="core",
             mentions=[Mention(start=2730, snippet="large language model")], chunk_ids=["c7"])
    c = Node(id="c", label="Raft", layer="core", mentions=[Mention(start=100)])
    edges = [Edge(id="e1", source="a", target="c"), Edge(id="e2", source="b", target="c")]
    nodes, out_edges, id_map = resolve([a, b, c], edges, use_embeddings=False)
    assert len(nodes) == 2
    merged = next(n for n in nodes if "LLM" in n.aliases or n.label == "LLM")
    assert merged.layer == "core"  # explicit discussion wins over jargon
    assert sorted(m.start for m in merged.mentions) == [615, 2730]
    assert set(merged.chunk_ids) == {"c1", "c7"}
    assert id_map["a"] == id_map["b"]
    assert len(out_edges) == 1  # duplicate edge collapsed


def test_embedding_merge_with_hash_backend():
    a = Node(id="a", label="Kubernetes", layer="core")
    b = Node(id="b", label="kubernetes cluster", layer="jargon")
    c = Node(id="c", label="Paxos", layer="jargon")
    nodes, _, _ = resolve([a, b, c], [], threshold=0.6)
    labels = sorted(n.label.lower() for n in nodes)
    assert "paxos" in labels and len(nodes) == 2


def test_prerequisite_not_duplicated_when_already_mentioned():
    a = Node(id="a", label="Quorum", layer="jargon")
    p = Node(id="p", label="Quorum", layer="prerequisite", inferred_from=["a"])
    nodes, _, _ = resolve([a, p], [], use_embeddings=False)
    assert len(nodes) == 1 and nodes[0].layer == "jargon"
