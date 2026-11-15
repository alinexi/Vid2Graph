"""Local-first text embeddings with graceful degradation.

Resolution order for ``auto``: Ollama → sentence-transformers → hash.
The *hash* embedder is a dependency-free character-trigram vectoriser. It is far
weaker than a neural model but still merges "LLM" / "LLMs" / "large language model"
reasonably, so entity resolution never silently turns off.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Any, Optional

from app.core import runtime_settings

log = logging.getLogger("vid2graph.embeddings")


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(x * x for x in b)) or 1e-9
    return dot / (na * nb)


class HashEmbedder:
    name = "hash"
    dim = 512

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            t = re.sub(r"[^a-z0-9 ]+", " ", t.lower())
            t = f"  {re.sub(r' +', ' ', t).strip()}  "
            vec = [0.0] * self.dim
            grams = [t[i:i + 3] for i in range(len(t) - 2)] + t.split()
            for g in grams:
                h = int(hashlib.blake2b(g.encode(), digest_size=4).hexdigest(), 16)
                vec[h % self.dim] += 1.0 if len(g) == 3 else 2.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class OllamaEmbedder:
    name = "ollama"

    def __init__(self, model: str, base_url: str):
        self.model, self.base = model, base_url.rstrip("/").removesuffix("/v1")

    def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx
        r = httpx.post(f"{self.base}/api/embed", json={"model": self.model, "input": texts}, timeout=120)
        r.raise_for_status()
        return r.json()["embeddings"]


class OpenAIEmbedder:
    name = "openai"

    def __init__(self, model: str, base_url: str, api_key: str):
        self.model, self.base, self.key = model, base_url, api_key

    def embed(self, texts: list[str]) -> list[list[float]]:
        import litellm
        kw: dict[str, Any] = {"api_key": self.key or "sk-local"}
        if self.base and "openai.com" not in self.base:
            kw["api_base"] = self.base if self.base.endswith("/v1") else self.base.rstrip("/") + "/v1"
        resp = litellm.embedding(model=f"openai/{self.model}", input=texts, **kw)
        return [d["embedding"] for d in resp.data]


class SentenceTransformerEmbedder:
    name = "sentence-transformers"

    def __init__(self, model: str):
        from sentence_transformers import SentenceTransformer  # type: ignore
        self.model = SentenceTransformer(model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self.model.encode(texts, normalize_embeddings=True)]


_cache: dict[tuple[str, str], list[float]] = {}


class Embedder:
    """Facade that picks a backend lazily and caches results per text."""

    def __init__(self):
        self.provider = runtime_settings.get("embedding_provider")
        self.model = runtime_settings.get("embedding_model")
        self.base = runtime_settings.get("embedding_base_url")
        self.key = runtime_settings.get("embedding_api_key")
        self._backend: Any = None

    def _pick(self) -> Any:
        if self._backend is not None:
            return self._backend
        order = {"auto": ["ollama", "sentence-transformers", "hash"]}.get(self.provider, [self.provider])
        for name in order:
            try:
                if name == "ollama":
                    b = OllamaEmbedder(self.model, self.base)
                    b.embed(["ping"])  # verify reachable + model pulled
                elif name == "sentence-transformers":
                    b = SentenceTransformerEmbedder("all-MiniLM-L6-v2" if self.model == "nomic-embed-text" else self.model)
                elif name == "openai":
                    b = OpenAIEmbedder(self.model, self.base, self.key)
                else:
                    b = HashEmbedder()
                self._backend = b
                log.info("embedding backend: %s", b.name)
                return b
            except Exception as exc:  # noqa: BLE001
                log.info("embedding backend %s unavailable (%s)", name, type(exc).__name__)
        self._backend = HashEmbedder()
        return self._backend

    @property
    def backend_name(self) -> str:
        return self._pick().name

    def embed(self, texts: list[str]) -> list[list[float]]:
        backend = self._pick()
        missing = [t for t in texts if (backend.name, t) not in _cache]
        if missing:
            for i in range(0, len(missing), 64):
                batch = missing[i:i + 64]
                try:
                    vecs = backend.embed(batch)
                except Exception as exc:  # noqa: BLE001
                    log.warning("embedding failed on %s (%s); using hash fallback", backend.name, exc)
                    self._backend = backend = HashEmbedder()
                    return self.embed(texts)
                for t, v in zip(batch, vecs):
                    _cache[(backend.name, t)] = v
        return [_cache[(backend.name, t)] for t in texts]

    def probe(self) -> dict[str, Any]:
        try:
            name = self.backend_name
            return {"provider": self.provider, "model": self.model, "backend": name,
                    "reachable": True, "detail": "pure-python fallback (weaker merging)" if name == "hash" else "ok"}
        except Exception as exc:  # noqa: BLE001
            return {"provider": self.provider, "model": self.model, "backend": None, "reachable": False, "detail": str(exc)}


_embedder: Optional[Embedder] = None


def get_embedder(fresh: bool = False) -> Embedder:
    global _embedder
    if _embedder is None or fresh:
        _embedder = Embedder()
    return _embedder
