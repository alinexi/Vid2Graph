from app.models.schemas import TranscriptSegment
from app.pipeline.chunker import chunk_transcript, fmt_ts, parse_ts


def _segs(n=120, step=10.0):
    return [TranscriptSegment(id=i, start=i * step, end=i * step + step - 0.5, text=f"segment {i} text") for i in range(n)]


def test_fmt_and_parse_roundtrip():
    assert fmt_ts(855) == "14:15"
    assert fmt_ts(3725) == "1:02:05"
    assert parse_ts("14:15") == 855
    assert parse_ts("1:02:05") == 3725
    assert parse_ts("[14:15]") == 855
    assert parse_ts("garbage") is None


def test_chunks_cover_everything_with_overlap():
    segs = _segs()  # 20 minutes
    chunks = chunk_transcript(segs, window_minutes=6, overlap_seconds=45)
    assert len(chunks) >= 4
    covered = {sid for c in chunks for sid in c.segment_ids}
    assert covered == {s.id for s in segs}
    for a, b in zip(chunks, chunks[1:]):
        assert b.start < a.end  # overlap
        assert b.start > a.start  # progress
    assert chunks[0].text.startswith("[00:00] segment 0")


def test_empty_transcript():
    assert chunk_transcript([]) == []
