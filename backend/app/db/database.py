"""Zero-config SQLite persistence.

Graphs are stored as JSON documents (transcript / chunks / nodes / edges in separate
columns so list views stay cheap). Access is serialised through a module-level lock —
SQLite is more than enough for a single-user local tool and keeps deployment to a
single file.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from app.models.schemas import Graph, GraphMeta, Job

_SCHEMA = """
CREATE TABLE IF NOT EXISTS graphs (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    status      TEXT NOT NULL,
    meta        TEXT NOT NULL,
    transcript  TEXT NOT NULL DEFAULT '[]',
    chunks      TEXT NOT NULL DEFAULT '[]',
    nodes       TEXT NOT NULL DEFAULT '[]',
    edges       TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    graph_id    TEXT NOT NULL,
    status      TEXT NOT NULL,
    payload     TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_graphs_created ON graphs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_graph ON jobs(graph_id);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        with self._tx() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── graphs ───────────────────────────────────────────────────────────────
    def save_graph(self, g: Graph) -> None:
        g.recompute_stats()
        meta = GraphMeta(**g.model_dump(include=set(GraphMeta.model_fields)))
        with self._tx() as c:
            c.execute(
                """INSERT INTO graphs (id,title,created_at,updated_at,status,meta,transcript,chunks,nodes,edges)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     title=excluded.title, updated_at=excluded.updated_at, status=excluded.status,
                     meta=excluded.meta, transcript=excluded.transcript, chunks=excluded.chunks,
                     nodes=excluded.nodes, edges=excluded.edges""",
                (
                    g.id, g.title, g.created_at, g.updated_at, g.status,
                    meta.model_dump_json(),
                    json.dumps([s.model_dump() for s in g.transcript]),
                    json.dumps([s.model_dump() for s in g.chunks]),
                    json.dumps([n.model_dump() for n in g.nodes]),
                    json.dumps([e.model_dump() for e in g.edges]),
                ),
            )

    def update_graph_meta(self, g: GraphMeta) -> None:
        with self._tx() as c:
            c.execute(
                "UPDATE graphs SET title=?, updated_at=?, status=?, meta=? WHERE id=?",
                (g.title, g.updated_at, g.status, g.model_dump_json(), g.id),
            )

    def get_graph(self, graph_id: str) -> Optional[Graph]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM graphs WHERE id=?", (graph_id,)).fetchone()
        if not row:
            return None
        meta = json.loads(row["meta"])
        return Graph(
            **meta,
            transcript=json.loads(row["transcript"]),
            chunks=json.loads(row["chunks"]),
            nodes=json.loads(row["nodes"]),
            edges=json.loads(row["edges"]),
        )

    def list_graphs(self) -> list[GraphMeta]:
        with self._lock:
            rows = self._conn.execute("SELECT meta FROM graphs ORDER BY created_at DESC").fetchall()
        return [GraphMeta(**json.loads(r["meta"])) for r in rows]

    def delete_graph(self, graph_id: str) -> bool:
        with self._tx() as c:
            cur = c.execute("DELETE FROM graphs WHERE id=?", (graph_id,))
            c.execute("DELETE FROM jobs WHERE graph_id=?", (graph_id,))
        return cur.rowcount > 0

    def count_graphs(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM graphs").fetchone()[0])

    def demo_exists(self) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT id FROM graphs WHERE id='demo-distributed-systems'").fetchone()
        return row is not None

    # ── jobs ─────────────────────────────────────────────────────────────────
    def save_job(self, job: Job) -> None:
        with self._tx() as c:
            c.execute(
                """INSERT INTO jobs (id, graph_id, status, payload, updated_at) VALUES (?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET status=excluded.status, payload=excluded.payload,
                   updated_at=excluded.updated_at""",
                (job.id, job.graph_id, job.status, job.model_dump_json(), job.updated_at),
            )

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM jobs WHERE id=?", (job_id,)).fetchone()
        return Job.model_validate_json(row["payload"]) if row else None

    def latest_job_for_graph(self, graph_id: str) -> Optional[Job]:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM jobs WHERE graph_id=? ORDER BY updated_at DESC LIMIT 1", (graph_id,)
            ).fetchone()
        return Job.model_validate_json(row["payload"]) if row else None

    # ── settings ─────────────────────────────────────────────────────────────
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )


_db: Optional[Database] = None


def get_db() -> Database:
    global _db
    if _db is None:
        from app.core.config import settings
        _db = Database(settings.db_path)
    return _db


def set_db(db: Database) -> None:
    global _db
    _db = db
