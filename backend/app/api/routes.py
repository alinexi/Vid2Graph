"""REST API. Everything the frontend needs lives under /api."""
from __future__ import annotations

import logging
import mimetypes
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response

from app import __version__
from app.core import runtime_settings
from app.core.config import settings
from app.core.llm import LLMError, get_llm
from app.db.database import Database, get_db
from app.db.seed_demo import DEMO_ID, seed_if_missing
from app.models.schemas import (ChatRequest, ChatResponse, ExpandResponse, Graph, GraphMeta, HealthResponse,
                                Job, new_id)
from app.pipeline import chat as chat_pipeline
from app.pipeline import graph_gen
from app.pipeline.embeddings import get_embedder
from app.pipeline.exporter import export_markdown, export_vault_zip, safe_filename
from app.pipeline.extractor import AUDIO_EXT, SUBTITLE_EXT, VIDEO_EXT, is_youtube, whisper_backend_info
from app.pipeline.jobs import get_runner
from app.pipeline.resolver import merge_into_graph

log = logging.getLogger("vid2graph.api")
router = APIRouter(prefix="/api")

MAX_UPLOAD_BYTES = 2 * 1024 ** 3  # 2 GB


def db_dep() -> Database:
    return get_db()


def _get_graph_or_404(db: Database, graph_id: str) -> Graph:
    g = db.get_graph(graph_id)
    if not g:
        raise HTTPException(404, f"graph {graph_id} not found")
    return g


# ── Health & settings ────────────────────────────────────────────────────────
@router.get("/health", response_model=HealthResponse)
def health(db: Database = Depends(db_dep)) -> HealthResponse:
    llm = get_llm().probe()
    return HealthResponse(status="ok", version=__version__, llm=llm, embeddings=get_embedder().probe(),
                          whisper=whisper_backend_info(), graphs=db.count_graphs())


@router.get("/settings")
def get_settings() -> dict:
    return {"settings": runtime_settings.current().masked(),
            "providers": ["ollama", "lmstudio", "vllm", "openai", "anthropic", "gemini", "groq", "openrouter",
                         "openai_compatible", "mock"],
            "whisper_backends": ["auto", "faster-whisper", "mlx", "whisper.cpp", "none"],
            "embedding_providers": ["auto", "ollama", "sentence-transformers", "openai", "hash"]}


@router.put("/settings")
def put_settings(values: dict, db: Database = Depends(db_dep)) -> dict:
    stored = runtime_settings.set_overrides(values)
    db.set_setting("model_overrides", stored)
    get_embedder(fresh=True)
    return {"settings": runtime_settings.current().masked()}


@router.post("/settings/test")
def test_settings(values: Optional[dict] = None) -> dict:
    """Probe connectivity for the given (unsaved) settings, or the current ones."""
    if values:
        snapshot = dict(runtime_settings._overrides)  # noqa: SLF001
        try:
            runtime_settings.set_overrides(values)
            return {"llm": get_llm().probe(), "embeddings": get_embedder(fresh=True).probe(), "whisper": whisper_backend_info()}
        finally:
            runtime_settings.load_overrides(snapshot)
            get_embedder(fresh=True)
    return {"llm": get_llm().probe(), "embeddings": get_embedder().probe(), "whisper": whisper_backend_info()}


# ── Ingestion ────────────────────────────────────────────────────────────────
@router.post("/ingest")
async def ingest(
    url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    title: Optional[str] = Form(None),
    language: str = Form("en"),
    force_whisper: bool = Form(False),
    db: Database = Depends(db_dep),
) -> dict:
    url = (url or "").strip()
    if not url and not file:
        raise HTTPException(400, "Provide a YouTube URL or upload a file")
    if url and not is_youtube(url):
        raise HTTPException(400, "Only YouTube URLs are supported for now. Upload a media or subtitle file instead.")

    # Fail fast with an actionable message instead of dying at 65% of the job.
    probe = get_llm().probe()
    if not probe["reachable"] or probe.get("model_available") is False:
        raise HTTPException(
            400, f"LLM is not ready ({probe['provider']}:{probe['model']}): {probe['detail']}. "
                 "Fix it in Settings (e.g. pick a hosted provider and paste an API key, or start Ollama), "
                 "or choose the 'mock' provider to try the app without a model.")

    graph_id = new_id("g_")
    graph = Graph(id=graph_id, title=(title or "").strip() or graph_id, language=language,
                  source_type="youtube" if url else "upload", source_url=url or None, status="pending")
    upload_path: Optional[Path] = None
    upload_name: Optional[str] = None
    if file:
        upload_name = file.filename or "upload"
        ext = Path(upload_name).suffix.lower()
        if ext not in SUBTITLE_EXT | AUDIO_EXT | VIDEO_EXT:
            raise HTTPException(400, f"Unsupported file type {ext}. Use .srt/.vtt/.txt or audio/video.")
        tmpdir = settings.resolved_data_dir / "tmp" / graph_id
        tmpdir.mkdir(parents=True, exist_ok=True)
        upload_path = tmpdir / f"upload{ext}"
        size = 0
        with upload_path.open("wb") as fh:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    fh.close()
                    shutil.rmtree(tmpdir, ignore_errors=True)
                    raise HTTPException(413, "File too large (2 GB limit)")
                fh.write(chunk)
        if ext in SUBTITLE_EXT:
            graph.source_type = "subtitle"
        if not title:
            graph.title = Path(upload_name).stem

    db.save_graph(graph)
    job = Job(graph_id=graph_id, message="Queued")
    db.save_job(job)
    get_runner(db).start(job, graph, url=url or None, upload_path=upload_path, upload_name=upload_name,
                         force_whisper=force_whisper)
    return {"job_id": job.id, "graph_id": graph_id}


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str, db: Database = Depends(db_dep)) -> Job:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


# ── Graphs ───────────────────────────────────────────────────────────────────
@router.get("/graphs", response_model=list[GraphMeta])
def list_graphs(db: Database = Depends(db_dep)) -> list[GraphMeta]:
    return db.list_graphs()


@router.get("/graphs/{graph_id}", response_model=Graph)
def get_graph(graph_id: str, db: Database = Depends(db_dep)) -> Graph:
    return _get_graph_or_404(db, graph_id)


@router.get("/graphs/{graph_id}/job", response_model=Optional[Job])
def get_graph_job(graph_id: str, db: Database = Depends(db_dep)) -> Optional[Job]:
    return db.latest_job_for_graph(graph_id)


@router.patch("/graphs/{graph_id}", response_model=GraphMeta)
def patch_graph(graph_id: str, body: dict, db: Database = Depends(db_dep)) -> GraphMeta:
    g = _get_graph_or_404(db, graph_id)
    if "title" in body and str(body["title"]).strip():
        g.title = str(body["title"]).strip()[:200]
    if "description" in body:
        g.description = str(body["description"])[:2000]
    if "media_url" in body:
        url = str(body["media_url"] or "").strip()
        if url and is_youtube(url):
            from app.pipeline.extractor import youtube_id
            g.media_kind, g.media_url, g.source_url = "youtube", youtube_id(url), url
        elif not url:
            g.media_kind, g.media_url = "none", None
    db.save_graph(g)
    return GraphMeta(**g.model_dump(include=set(GraphMeta.model_fields)))


@router.delete("/graphs/{graph_id}")
def delete_graph(graph_id: str, db: Database = Depends(db_dep)) -> dict:
    if not db.delete_graph(graph_id):
        raise HTTPException(404, "graph not found")
    for f in (settings.resolved_data_dir / "media").glob(f"{graph_id}.*"):
        f.unlink(missing_ok=True)
    return {"deleted": graph_id}


@router.post("/graphs/{graph_id}/nodes/{node_id}/expand", response_model=ExpandResponse)
def expand(graph_id: str, node_id: str, db: Database = Depends(db_dep)) -> ExpandResponse:
    g = _get_graph_or_404(db, graph_id)
    node = g.node_by_id(node_id)
    if not node:
        raise HTTPException(404, "node not found")
    try:
        new_nodes = graph_gen.expand_node(get_llm(), node, g.nodes)
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from exc
    new_edges = graph_gen.prerequisite_edges(new_nodes)
    nodes, edges, new_ids, new_edge_ids = merge_into_graph(g.nodes, g.edges, new_nodes, new_edges)
    g.nodes, g.edges = nodes, edges
    n2 = g.node_by_id(node_id)
    if n2:
        n2.expanded = True
    db.save_graph(g)
    return ExpandResponse(graph=g, new_node_ids=new_ids, new_edge_ids=new_edge_ids)


@router.post("/graphs/{graph_id}/chat", response_model=ChatResponse)
def graph_chat(graph_id: str, req: ChatRequest, db: Database = Depends(db_dep)) -> ChatResponse:
    g = _get_graph_or_404(db, graph_id)
    try:
        return chat_pipeline.answer(get_llm(), g, req)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/graphs/{graph_id}/export")
def export(graph_id: str, request: Request, format: str = Query("markdown", pattern="^(markdown|vault)$"),
           db: Database = Depends(db_dep)) -> Response:
    g = _get_graph_or_404(db, graph_id)
    origin = request.headers.get("origin") or settings.cors_origin_list[0]
    name = safe_filename(g.title)[:80] or g.id
    if format == "vault":
        data = export_vault_zip(g, app_url=origin)
        return Response(data, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'})
    md = export_markdown(g, app_url=origin)
    return PlainTextResponse(md, media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="{name}.md"'})


@router.get("/media/{graph_id}")
def media(graph_id: str, db: Database = Depends(db_dep)) -> FileResponse:
    files = list((settings.resolved_data_dir / "media").glob(f"{graph_id}.*"))
    if not files:
        raise HTTPException(404, "no media for this graph")
    mt = mimetypes.guess_type(files[0].name)[0] or "application/octet-stream"
    return FileResponse(files[0], media_type=mt)


@router.post("/demo/reset", response_model=Graph)
def reset_demo(db: Database = Depends(db_dep)) -> Graph:
    seed_if_missing(db, force=True)
    return _get_graph_or_404(db, DEMO_ID)
