"""Stage 2 — timestamp-preserving semantic chunking.

Small local models degrade sharply past a few thousand tokens, so we feed them
5-8 minute windows with a short overlap. Each utterance keeps a ``[mm:ss]`` marker
so the model can quote exact timestamps back to us.
"""
from __future__ import annotations

from app.models.schemas import Chunk, TranscriptSegment


def fmt_ts(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def parse_ts(value: str | float | int | None) -> float | None:
    """'1:02:03' | '14:15' | '855' | 855.0 → seconds (None when unparsable)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    v = str(value).strip().strip("[]")
    if not v:
        return None
    try:
        parts = [float(p) for p in v.split(":")]
    except ValueError:
        return None
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return None


def render_segments(segments: list[TranscriptSegment]) -> str:
    return "\n".join(f"[{fmt_ts(s.start)}] {s.text}" for s in segments)


def chunk_transcript(segments: list[TranscriptSegment], window_minutes: float = 6,
                     overlap_seconds: float = 45, max_chars: int = 9000) -> list[Chunk]:
    """Split by time window, additionally capping characters for very dense speech."""
    if not segments:
        return []
    window = window_minutes * 60
    chunks: list[Chunk] = []
    i = 0
    n = len(segments)
    while i < n:
        start_t = segments[i].start
        j = i
        chars = 0
        while j < n and segments[j].start - start_t < window:
            chars += len(segments[j].text) + 10
            if chars > max_chars and j > i:
                break
            j += 1
        j = max(j, i + 1)
        body = segments[i:j]
        chunks.append(Chunk(
            id=f"c{len(chunks)}", index=len(chunks),
            start=body[0].start, end=body[-1].end,
            text=render_segments(body), segment_ids=[s.id for s in body],
        ))
        if j >= n:
            break
        # step back for overlap, but always make progress
        next_start_t = segments[j - 1].end - overlap_seconds
        k = j
        while k - 1 > i and segments[k - 1].start > next_start_t:
            k -= 1
        i = max(k, i + 1)
    return chunks


def segments_in_range(segments: list[TranscriptSegment], start: float, end: float) -> list[TranscriptSegment]:
    return [s for s in segments if s.end >= start and s.start <= end]
