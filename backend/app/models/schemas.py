"""Pydantic models shared by the pipeline, the database layer and the API."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

Layer = Literal["core", "jargon", "prerequisite"]
Difficulty = Literal["beginner", "intermediate", "advanced"]
RelationType = Literal[
    "prerequisite_for", "compared_with", "part_of", "uses", "leads_to",
    "contrasts_with", "example_of", "related_to",
]
MediaKind = Literal["youtube", "video", "audio", "none"]
SourceType = Literal["youtube", "upload", "subtitle", "demo"]
GraphStatus = Literal["pending", "processing", "ready", "failed"]

DIFFICULTY_RANK: dict[str, int] = {"beginner": 0, "intermediate": 1, "advanced": 2}
LAYER_RANK: dict[str, int] = {"core": 0, "jargon": 1, "prerequisite": 2}


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Transcript ───────────────────────────────────────────────────────────────
class TranscriptSegment(BaseModel):
    id: int
    start: float
    end: float
    text: str
    speaker: Optional[str] = None


class Chunk(BaseModel):
    id: str
    index: int
    start: float
    end: float
    text: str
    segment_ids: list[int] = Field(default_factory=list)


# ── Graph ────────────────────────────────────────────────────────────────────
class Mention(BaseModel):
    """One place in the media where a concept is mentioned."""
    start: float
    end: Optional[float] = None
    snippet: str = ""
    chunk_id: Optional[str] = None


class Node(BaseModel):
    id: str = Field(default_factory=lambda: new_id("n_"))
    label: str
    aliases: list[str] = Field(default_factory=list)
    layer: Layer
    difficulty: Difficulty = "intermediate"
    eli5: str = ""
    summary: str = ""
    mentions: list[Mention] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)
    expanded: bool = False
    inferred_from: list[str] = Field(default_factory=list)  # node ids a prerequisite was inferred for

    @property
    def first_mention(self) -> Optional[Mention]:
        return min(self.mentions, key=lambda m: m.start) if self.mentions else None


class Edge(BaseModel):
    id: str = Field(default_factory=lambda: new_id("e_"))
    source: str
    target: str
    relation: RelationType = "related_to"
    label: Optional[str] = None


class GraphStats(BaseModel):
    nodes: int = 0
    edges: int = 0
    core: int = 0
    jargon: int = 0
    prerequisite: int = 0
    merged: int = 0
    chunks: int = 0
    duration: float = 0


class GraphMeta(BaseModel):
    id: str
    title: str
    description: str = ""
    source_type: SourceType = "subtitle"
    source_url: Optional[str] = None
    media_kind: MediaKind = "none"
    media_url: Optional[str] = None   # youtube id, or /api/media/{id}
    duration: float = 0
    language: str = "en"
    status: GraphStatus = "pending"
    model_used: str = ""
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)
    stats: GraphStats = Field(default_factory=GraphStats)
    is_demo: bool = False


class Graph(GraphMeta):
    transcript: list[TranscriptSegment] = Field(default_factory=list)
    chunks: list[Chunk] = Field(default_factory=list)
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)

    def recompute_stats(self) -> None:
        self.stats = GraphStats(
            nodes=len(self.nodes),
            edges=len(self.edges),
            core=sum(n.layer == "core" for n in self.nodes),
            jargon=sum(n.layer == "jargon" for n in self.nodes),
            prerequisite=sum(n.layer == "prerequisite" for n in self.nodes),
            merged=sum(len(n.aliases) > 0 for n in self.nodes),
            chunks=len(self.chunks),
            duration=self.duration,
        )
        self.updated_at = utcnow()

    def node_by_id(self, node_id: str) -> Optional[Node]:
        return next((n for n in self.nodes if n.id == node_id), None)


# ── Jobs ─────────────────────────────────────────────────────────────────────
JobStatus = Literal["queued", "running", "done", "failed"]


class Job(BaseModel):
    id: str = Field(default_factory=lambda: new_id("job_"))
    graph_id: str
    status: JobStatus = "queued"
    stage: str = "queued"
    progress: float = 0.0  # 0..1
    message: str = ""
    error: Optional[str] = None
    log: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)


# ── API request / response models ────────────────────────────────────────────
class IngestOptions(BaseModel):
    title: Optional[str] = None
    language: str = "en"
    force_whisper: bool = False


class ExpandResponse(BaseModel):
    graph: Graph
    new_node_ids: list[str]
    new_edge_ids: list[str]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    node_ids: list[str] = Field(min_length=1, max_length=3)
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=12)


class Citation(BaseModel):
    start: float
    text: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    context_chunks: list[str]


class HealthResponse(BaseModel):
    status: str
    version: str
    llm: dict
    embeddings: dict
    whisper: dict
    graphs: int
