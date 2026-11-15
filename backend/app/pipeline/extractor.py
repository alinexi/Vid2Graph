"""Stage 1 — ingestion & transcription.

Priority order (cheapest first):
1. User-supplied ``.srt`` / ``.vtt`` → parsed directly (zero GPU).
2. YouTube URL → ``yt-dlp`` fetches manual or auto-generated captions (zero GPU).
3. Otherwise download/upload audio → local Whisper (faster-whisper / mlx / whisper.cpp).
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app.core import runtime_settings
from app.models.schemas import TranscriptSegment

log = logging.getLogger("vid2graph.extractor")
Progress = Callable[[str, float], None]

AUDIO_EXT = {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac", ".opus", ".webm"}
VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".m4v"}
SUBTITLE_EXT = {".srt", ".vtt", ".txt"}


@dataclass
class IngestResult:
    segments: list[TranscriptSegment]
    title: str = ""
    duration: float = 0.0
    media_kind: str = "none"           # youtube | video | audio | none
    media_ref: Optional[str] = None     # youtube id or local path
    source_type: str = "subtitle"
    source_url: Optional[str] = None
    language: str = "en"
    notes: list[str] = field(default_factory=list)


# ── Subtitle parsing ─────────────────────────────────────────────────────────
_TS = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
_TAG = re.compile(r"<[^>]+>")
_CUE_LINE = re.compile(r"-->")


def _ts_to_seconds(s: str) -> float:
    m = _TS.search(s)
    if not m:
        raise ValueError(f"bad timestamp {s!r}")
    h, mi, se, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(se) + int(ms.ljust(3, "0")) / 1000


def parse_subtitles(text: str) -> list[TranscriptSegment]:
    """Parse SRT or WebVTT (incl. YouTube auto-captions with rolling duplicate lines)."""
    text = text.replace("\r\n", "\n").replace("﻿", "")
    lines = text.split("\n")
    cues: list[tuple[float, float, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if _CUE_LINE.search(line):
            try:
                a, b = line.split("-->")[:2]
                start, end = _ts_to_seconds(a), _ts_to_seconds(b.strip().split(" ")[0])
            except ValueError:
                i += 1
                continue
            i += 1
            body: list[str] = []
            while i < len(lines) and lines[i].strip() != "":
                body.append(lines[i])
                i += 1
            # YouTube auto-subs carry per-word timing tags and echo the previous line.
            clean = [_TAG.sub("", b).strip() for b in body]
            clean = [c for c in clean if c and not re.fullmatch(r"\d+", c)]
            if clean:
                cues.append((start, end, " ".join(clean)))
        i += 1

    # Dedupe rolling captions: drop text already emitted by the previous cue.
    segs: list[TranscriptSegment] = []
    prev_text = ""
    for start, end, body in cues:
        body = re.sub(r"\s+", " ", body).strip()
        if not body:
            continue
        if prev_text and body.startswith(prev_text):
            body = body[len(prev_text):].strip()
        elif prev_text and prev_text.endswith(body):
            continue
        if not body:
            prev_text = ""  # the next cue will carry fresh text
            continue
        if segs and start < segs[-1].end:
            start = segs[-1].end
        if end <= start:
            end = start + max(0.5, len(body) / 15)
        prev_text_candidate = body
        segs.append(TranscriptSegment(id=len(segs), start=round(start, 3), end=round(end, 3), text=body))
        prev_text = prev_text_candidate
    return _merge_fragments(segs)


def _merge_fragments(segs: list[TranscriptSegment], min_chars: int = 40) -> list[TranscriptSegment]:
    """Auto-captions come in 2-4 word fragments; merge into sentence-ish segments."""
    if not segs:
        return segs
    merged: list[TranscriptSegment] = []
    cur = segs[0].model_copy()
    for s in segs[1:]:
        gap = s.start - cur.end
        ends_sentence = cur.text.rstrip().endswith((".", "?", "!"))
        if len(cur.text) < min_chars and gap < 1.5 and not ends_sentence:
            cur.text = f"{cur.text} {s.text}".strip()
            cur.end = s.end
        else:
            merged.append(cur)
            cur = s.model_copy()
    merged.append(cur)
    for idx, m in enumerate(merged):
        m.id = idx
    return merged


def parse_plain_text(text: str, words_per_minute: float = 150) -> list[TranscriptSegment]:
    """Fallback for transcripts without timestamps: assign synthetic timing by WPM."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    segs, t = [], 0.0
    for idx, s in enumerate(sentences):
        dur = max(1.0, len(s.split()) / words_per_minute * 60)
        segs.append(TranscriptSegment(id=idx, start=round(t, 2), end=round(t + dur, 2), text=s))
        t += dur
    return segs


# ── YouTube ──────────────────────────────────────────────────────────────────
_YT_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})")


def youtube_id(url: str) -> Optional[str]:
    m = _YT_ID.search(url)
    return m.group(1) if m else None


def is_youtube(url: str) -> bool:
    return bool(re.search(r"(youtube\.com|youtu\.be)", url))


def fetch_youtube(url: str, workdir: Path, language: str = "en",
                  force_whisper: bool = False, progress: Optional[Progress] = None) -> IngestResult:
    import yt_dlp  # type: ignore

    progress = progress or (lambda *_: None)
    vid = youtube_id(url) or "video"
    workdir.mkdir(parents=True, exist_ok=True)
    langs = [language, f"{language}-*", f"{language}.*"]
    progress("Fetching video metadata & captions via yt-dlp", 0.05)

    ydl_opts = {
        "skip_download": True,
        "writesubtitles": not force_whisper,
        "writeautomaticsub": not force_whisper,
        "subtitleslangs": langs,
        "subtitlesformat": "vtt/srt/best",
        "outtmpl": str(workdir / "%(id)s.%(ext)s"),
        "quiet": True, "no_warnings": True, "noprogress": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    title = info.get("title") or vid
    duration = float(info.get("duration") or 0)

    result = IngestResult(segments=[], title=title, duration=duration, media_kind="youtube",
                          media_ref=info.get("id", vid), source_type="youtube", source_url=url, language=language)

    if not force_whisper:
        sub_files = sorted(workdir.glob(f"{info.get('id', vid)}*.vtt")) + sorted(workdir.glob(f"{info.get('id', vid)}*.srt"))
        for sf in sub_files:
            segs = parse_subtitles(sf.read_text(encoding="utf-8", errors="ignore"))
            if len(segs) >= 3:
                result.segments = segs
                result.notes.append(f"captions: {sf.name}")
                progress(f"Captions found ({len(segs)} segments) — skipping Whisper", 0.2)
                return result
        progress("No captions available — downloading audio for local Whisper", 0.1)

    audio = _download_youtube_audio(url, workdir)
    result.segments = transcribe(audio, language=language, progress=progress)
    result.notes.append("transcribed with whisper")
    return result


def _download_youtube_audio(url: str, workdir: Path) -> Path:
    import yt_dlp  # type: ignore

    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": str(workdir / "audio.%(ext)s"),
        "quiet": True, "no_warnings": True, "noprogress": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
    if not path.exists():
        cands = list(workdir.glob("audio.*"))
        if not cands:
            raise RuntimeError("yt-dlp did not produce an audio file")
        path = cands[0]
    return path


# ── Whisper backends ─────────────────────────────────────────────────────────
def whisper_backend_info() -> dict:
    backend = runtime_settings.get("whisper_backend")
    avail = {}
    for mod, name in (("faster_whisper", "faster-whisper"), ("mlx_whisper", "mlx")):
        try:
            __import__(mod)
            avail[name] = True
        except Exception:  # noqa: BLE001
            avail[name] = False
    avail["whisper.cpp"] = shutil.which(runtime_settings.get("whisper_cpp_bin")) is not None
    chosen = _pick_whisper_backend(backend, avail)
    return {"configured": backend, "resolved": chosen, "model": runtime_settings.get("whisper_model"),
            "available": avail, "device": runtime_settings.get("whisper_device")}


def _pick_whisper_backend(backend: str, avail: dict) -> Optional[str]:
    if backend == "none":
        return None
    if backend != "auto":
        return backend if avail.get(backend) else None
    for name in ("faster-whisper", "mlx", "whisper.cpp"):
        if avail.get(name):
            return name
    return None


def transcribe(path: Path, language: str = "en", progress: Optional[Progress] = None) -> list[TranscriptSegment]:
    progress = progress or (lambda *_: None)
    info = whisper_backend_info()
    backend = info["resolved"]
    if backend is None:
        raise RuntimeError(
            "No captions found and no speech-to-text backend is available. "
            "Install one with `pip install faster-whisper` (or mlx-whisper on Apple Silicon), "
            "or upload an .srt/.vtt file instead."
        )
    model = runtime_settings.get("whisper_model")
    progress(f"Transcribing with {backend} ({model}) — this can take a while", 0.15)
    if backend == "faster-whisper":
        return _transcribe_faster_whisper(path, model, language, progress)
    if backend == "mlx":
        return _transcribe_mlx(path, model, language)
    if backend == "whisper.cpp":
        return _transcribe_whisper_cpp(path, language)
    raise RuntimeError(f"unknown whisper backend {backend}")


def _transcribe_faster_whisper(path: Path, model: str, language: str, progress: Progress) -> list[TranscriptSegment]:
    from faster_whisper import WhisperModel  # type: ignore

    device = runtime_settings.get("whisper_device")
    compute = runtime_settings.get("whisper_compute_type")
    if device == "auto":
        try:
            import ctranslate2  # type: ignore
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:  # noqa: BLE001
            device = "cpu"
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"
    wm = WhisperModel(model, device=device, compute_type=compute)
    segments_iter, info = wm.transcribe(str(path), language=language or None, vad_filter=True, beam_size=1)
    total = float(info.duration or 0) or 1.0
    segs: list[TranscriptSegment] = []
    for s in segments_iter:
        segs.append(TranscriptSegment(id=len(segs), start=round(s.start, 3), end=round(s.end, 3), text=s.text.strip()))
        if len(segs) % 20 == 0:
            progress(f"Transcribing… {int(min(s.end / total, 1) * 100)}%", 0.15 + 0.25 * min(s.end / total, 1))
    return segs


def _transcribe_mlx(path: Path, model: str, language: str) -> list[TranscriptSegment]:
    import mlx_whisper  # type: ignore

    repo = model if "/" in model else f"mlx-community/whisper-{model}-mlx"
    out = mlx_whisper.transcribe(str(path), path_or_hf_repo=repo, language=language or None)
    return [TranscriptSegment(id=i, start=round(s["start"], 3), end=round(s["end"], 3), text=s["text"].strip())
            for i, s in enumerate(out["segments"])]


def _transcribe_whisper_cpp(path: Path, language: str) -> list[TranscriptSegment]:
    binary = runtime_settings.get("whisper_cpp_bin")
    model = runtime_settings.get("whisper_cpp_model")
    if not model:
        raise RuntimeError("VID2GRAPH_WHISPER_CPP_MODEL must point at a ggml model file")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out"
        cmd = [binary, "-m", model, "-f", str(path), "-l", language or "auto", "-osrt", "-of", str(out)]
        subprocess.run(cmd, check=True, capture_output=True)
        return parse_subtitles((out.with_suffix(".srt")).read_text(encoding="utf-8", errors="ignore"))


# ── Local uploads ────────────────────────────────────────────────────────────
def ingest_upload(path: Path, filename: str, language: str = "en",
                  progress: Optional[Progress] = None) -> IngestResult:
    progress = progress or (lambda *_: None)
    ext = Path(filename).suffix.lower()
    if ext in SUBTITLE_EXT:
        text = path.read_text(encoding="utf-8", errors="ignore")
        segs = parse_subtitles(text) if ext != ".txt" or "-->" in text else parse_plain_text(text)
        progress(f"Parsed {len(segs)} subtitle segments", 0.2)
        return IngestResult(segments=segs, title=Path(filename).stem, duration=segs[-1].end if segs else 0,
                            media_kind="none", source_type="subtitle", language=language,
                            notes=["parsed from subtitle file"])
    if ext in AUDIO_EXT or ext in VIDEO_EXT:
        segs = transcribe(path, language=language, progress=progress)
        kind = "video" if ext in VIDEO_EXT else "audio"
        return IngestResult(segments=segs, title=Path(filename).stem, duration=segs[-1].end if segs else 0,
                            media_kind=kind, media_ref=str(path), source_type="upload", language=language,
                            notes=["transcribed with whisper"])
    raise ValueError(f"Unsupported file type {ext!r}. Upload .srt/.vtt/.txt or audio/video.")
