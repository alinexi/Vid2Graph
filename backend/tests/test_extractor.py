from app.pipeline.extractor import parse_plain_text, parse_subtitles, youtube_id

SRT = """1
00:00:01,000 --> 00:00:04,000
Hello and welcome to the show.

2
00:00:04,500 --> 00:00:07,000
Today we talk about Raft.
"""

VTT_AUTO = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000 align:start position:0%
 
we<00:00:00.500><c> ran</c><00:00:00.800><c> into</c>

00:00:02.000 --> 00:00:02.010 align:start position:0%
we ran into
 

00:00:02.010 --> 00:00:04.000 align:start position:0%
we ran into
split<00:00:02.500><c> brain</c><00:00:03.000><c> issues</c>
"""


def test_parse_srt():
    segs = parse_subtitles(SRT)
    assert len(segs) == 2
    assert segs[0].start == 1.0 and segs[0].end == 4.0
    assert "Raft" in segs[1].text


def test_parse_youtube_auto_vtt_dedupes_rolling_lines():
    segs = parse_subtitles(VTT_AUTO)
    text = " ".join(s.text for s in segs)
    assert text.count("we ran into") == 1
    assert "split brain issues" in text


def test_plain_text_fallback_assigns_timing():
    segs = parse_plain_text("First sentence here. Second sentence follows! Third?")
    assert len(segs) == 3
    assert segs[1].start >= segs[0].end


def test_youtube_id():
    assert youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1s") == "dQw4w9WgXcQ"
    assert youtube_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube_id("https://example.com") is None
