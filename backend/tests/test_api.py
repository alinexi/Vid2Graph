import io
import time

from app.db.seed_demo import DEMO_ID

SRT = """1
00:00:01,000 --> 00:00:05,000
We ran into Split-Brain issues in production early on.

2
00:00:05,500 --> 00:00:10,000
So we had to migrate from Paxos to Raft to achieve reliable Consensus.

3
00:00:10,500 --> 00:00:15,000
Our Fencing Tokens stopped stale leaders from writing.
"""


def test_health_and_demo_seeded(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["llm"]["provider"] == "mock" and body["graphs"] >= 1
    graphs = client.get("/api/graphs").json()
    assert any(g["id"] == DEMO_ID and g["is_demo"] for g in graphs)


def test_demo_graph_reference_scenario(client):
    g = client.get(f"/api/graphs/{DEMO_ID}").json()
    by_label = {n["label"]: n for n in g["nodes"]}
    sb = by_label["Split-Brain"]
    assert sb["layer"] == "jargon"
    assert any(int(m["start"]) == 855 for m in sb["mentions"])  # 14:15
    assert by_label["Distributed Consensus"]["layer"] == "prerequisite"
    assert by_label["Quorum"]["layer"] == "prerequisite"
    assert by_label["Team Migration to Raft"]["layer"] == "core"
    ids = {n["id"]: n for n in g["nodes"]}
    rel = {(ids[e["source"]]["label"], ids[e["target"]]["label"], e["relation"]) for e in g["edges"]}
    assert ("Paxos", "Team Migration to Raft", "compared_with") in rel
    assert ("Distributed Consensus", "Split-Brain", "prerequisite_for") in rel
    assert all(e["source"] in ids and e["target"] in ids for e in g["edges"])
    seg = next(s for s in g["transcript"] if s["start"] == 855)
    assert "Split-Brain" in seg["text"]


def test_ingest_subtitle_end_to_end(client):
    r = client.post("/api/ingest", data={"title": "Test talk"},
                    files={"file": ("talk.srt", io.BytesIO(SRT.encode()), "text/plain")})
    assert r.status_code == 200, r.text
    job_id, graph_id = r.json()["job_id"], r.json()["graph_id"]
    for _ in range(100):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert job["status"] == "done", job
    g = client.get(f"/api/graphs/{graph_id}").json()
    assert g["status"] == "ready" and g["title"] == "Test talk"
    assert g["stats"]["nodes"] > 0 and g["stats"]["prerequisite"] > 0
    assert g["media_kind"] == "none" and len(g["transcript"]) == 3

    # expand
    node = next(n for n in g["nodes"] if n["layer"] != "prerequisite")
    r = client.post(f"/api/graphs/{graph_id}/nodes/{node['id']}/expand")
    assert r.status_code == 200 and len(r.json()["new_node_ids"]) >= 1

    # chat
    r = client.post(f"/api/graphs/{graph_id}/chat", json={"node_ids": [node["id"]], "question": "What was said?"})
    assert r.status_code == 200 and r.json()["answer"]

    # export
    md = client.get(f"/api/graphs/{graph_id}/export?format=markdown")
    assert md.status_code == 200 and "[[" in md.text and "?graph=" in md.text
    zp = client.get(f"/api/graphs/{graph_id}/export?format=vault")
    assert zp.status_code == 200 and zp.headers["content-type"] == "application/zip"

    # delete
    assert client.delete(f"/api/graphs/{graph_id}").status_code == 200
    assert client.get(f"/api/graphs/{graph_id}").status_code == 404


def test_ingest_rejects_bad_input(client):
    assert client.post("/api/ingest", data={}).status_code == 400
    assert client.post("/api/ingest", data={"url": "https://vimeo.com/123"}).status_code == 400


def test_settings_roundtrip(client):
    r = client.put("/api/settings", json={"llm_model": "qwen2.5:14b", "llm_api_key": "sk-secret-1234"})
    s = r.json()["settings"]
    assert s["llm_model"] == "qwen2.5:14b"
    assert s["llm_api_key"].endswith("1234") and s["llm_api_key"].startswith("•")
    # sending the mask back must not overwrite the secret
    client.put("/api/settings", json={"llm_api_key": s["llm_api_key"]})
    from app.core import runtime_settings
    assert runtime_settings.get("llm_api_key") == "sk-secret-1234"
    client.put("/api/settings", json={"llm_model": "qwen2.5:7b", "llm_api_key": ""})


def test_export_demo_markdown_has_youtube_or_app_links(client):
    md = client.get(f"/api/graphs/{DEMO_ID}/export").text
    assert "# From Paxos to Raft" in md
    assert "[[Split-Brain]]" in md
    assert "14:15" in md
