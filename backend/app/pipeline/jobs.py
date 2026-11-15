"""Background processing: ingest → chunk → extract → resolve → enrich → persist.

Jobs run on a daemon thread (the pipeline is CPU/IO bound in C libraries and
network calls, so the GIL is not a bottleneck) and report progress to SQLite so
the UI can poll ``GET /api/jobs/{id}``.
"""
from __future__ import annotations

import logging
import shutil
import threading
import traceback
from pathlib import Path
from typing import Optional

from app.core import runtime_settings
from app.core.config import settings
from app.core.llm import get_llm
from app.db.database import Database
from app.models.schemas import Graph, Job, utcnow
from app.pipeline import graph_gen
from app.pipeline.chunker import chunk_transcript
from app.pipeline.extractor import IngestResult, fetch_youtube, ingest_upload
from app.pipeline.resolver import resolve

log = logging.getLogger("vid2graph.jobs")


class JobRunner:
    def __init__(self, db: Database):
        self.db = db
        self._threads: dict[str, threading.Thread] = {}

    # ── progress helpers ─────────────────────────────────────────────────────
    def _update(self, job: Job, stage: str, message: str, progress: float, status: str = "running") -> None:
        job.stage, job.message, job.progress, job.status = stage, message, max(job.progress, progress), status
        job.updated_at = utcnow()
        job.log.append(f"{job.updated_at[11:19]} {message}")
        job.log = job.log[-200:]
        self.db.save_job(job)
        log.info("[%s] %s (%.0f%%)", job.graph_id, message, progress * 100)

    # ── public API ───────────────────────────────────────────────────────────
    def start(self, job: Job, graph: Graph, *, url: Optional[str] = None,
              upload_path: Optional[Path] = None, upload_name: Optional[str] = None,
              force_whisper: bool = False) -> None:
        t = threading.Thread(
            target=self._run, args=(job, graph, url, upload_path, upload_name, force_whisper),
            name=f"vid2graph-job-{job.id}", daemon=True,
        )
        self._threads[job.id] = t
        t.start()

    def _run(self, job: Job, graph: Graph, url: Optional[str], upload_path: Optional[Path],
             upload_name: Optional[str], force_whisper: bool) -> None:
        workdir = settings.resolved_data_dir / "tmp" / graph.id
        try:
            progress = lambda msg, p: self._update(job, "ingest" if p < 0.3 else "extract", msg, p)  # noqa: E731
            self._update(job, "ingest", "Starting ingestion", 0.02)

            # ── Stage 1: ingestion ───────────────────────────────────────────
            if url:
                res = fetch_youtube(url, workdir, language=graph.language, force_whisper=force_whisper, progress=progress)
            elif upload_path:
                res = ingest_upload(upload_path, upload_name or upload_path.name, language=graph.language, progress=progress)
            else:
                raise ValueError("Nothing to ingest")
            self._apply_ingest(graph, res)
            if not graph.transcript:
                raise RuntimeError("Transcript is empty — nothing to extract.")
            graph.status = "processing"
            self.db.save_graph(graph)
            self._update(job, "chunk", f"Transcript ready: {len(graph.transcript)} segments, "
                                       f"{graph.duration / 60:.0f} min", 0.3)

            # ── Stage 2: chunking ────────────────────────────────────────────
            graph.chunks = chunk_transcript(
                graph.transcript,
                window_minutes=float(runtime_settings.get("chunk_minutes")),
                overlap_seconds=float(runtime_settings.get("chunk_overlap_seconds")),
            )
            self._update(job, "extract", f"Split into {len(graph.chunks)} timestamped chunks", 0.33)

            # ── Stage 3: two-pass extraction ─────────────────────────────────
            llm = get_llm()
            graph.model_used = llm.describe
            raw_nodes = graph_gen.pass1_extract(llm, graph.chunks, progress=lambda m, p: self._update(job, "extract", m, p))
            self._update(job, "resolve", f"Merging synonyms across {len(raw_nodes)} raw concepts", 0.66)
            nodes, edges, _ = resolve(raw_nodes, [])
            self._update(job, "enrich", f"{len(nodes)} unique concepts after entity resolution", 0.67)
            graph_gen.pass2_enrich(llm, nodes, progress=lambda m, p: self._update(job, "enrich", m, p))
            prereqs, rel_edges = graph_gen.pass2_synthesize(llm, nodes, progress=lambda m, p: self._update(job, "synthesize", m, p))
            edges = rel_edges + graph_gen.prerequisite_edges(prereqs)

            # ── Stage 4: final resolution incl. prerequisites ────────────────
            self._update(job, "resolve", "Final entity resolution & graph assembly", 0.9)
            nodes, edges, _ = resolve(nodes + prereqs, edges)
            graph.nodes, graph.edges = nodes, edges
            if not graph.title or graph.title == graph.id:
                graph.title, graph.description = graph_gen.generate_title(llm, nodes, graph.title or "Untitled video")
            elif not graph.description:
                _, graph.description = graph_gen.generate_title(llm, nodes, graph.title)
            graph.status = "ready"
            self.db.save_graph(graph)
            self._update(job, "done", f"Done: {len(nodes)} nodes, {len(edges)} edges", 1.0, status="done")
        except Exception as exc:  # noqa: BLE001
            log.error("job %s failed: %s\n%s", job.id, exc, traceback.format_exc())
            graph.status = "failed"
            graph.description = f"Processing failed: {exc}"
            self.db.save_graph(graph)
            job.error = str(exc)
            self._update(job, "failed", f"Failed: {exc}", job.progress, status="failed")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
            self._threads.pop(job.id, None)

    def _apply_ingest(self, graph: Graph, res: IngestResult) -> None:
        graph.transcript = res.segments
        graph.duration = res.duration or (res.segments[-1].end if res.segments else 0)
        graph.source_type = res.source_type  # type: ignore[assignment]
        graph.source_url = res.source_url or graph.source_url
        graph.language = res.language
        if not graph.title or graph.title == graph.id:
            graph.title = res.title or graph.title
        graph.media_kind = res.media_kind  # type: ignore[assignment]
        if res.media_kind == "youtube":
            graph.media_url = res.media_ref
        elif res.media_kind in ("video", "audio") and res.media_ref:
            # move uploaded media into the persistent media dir, served by /api/media/{id}
            src = Path(res.media_ref)
            dest = settings.resolved_data_dir / "media" / f"{graph.id}{src.suffix.lower()}"
            if src.resolve() != dest.resolve():
                shutil.move(str(src), str(dest))
            graph.media_url = f"/api/media/{graph.id}"
        else:
            graph.media_url = None
        if res.notes:
            graph.description = "; ".join(res.notes)


_runner: Optional[JobRunner] = None


def get_runner(db: Database) -> JobRunner:
    global _runner
    if _runner is None or _runner.db is not db:
        _runner = JobRunner(db)
    return _runner
