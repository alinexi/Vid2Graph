"""Runtime-editable model settings (what the UI's settings modal edits).

The values persist in SQLite so a user can switch from Ollama to LM Studio without
restarting the server. Anything not overridden falls back to :data:`settings`.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.core.config import settings

EDITABLE_KEYS = {
    "llm_provider", "llm_model", "llm_base_url", "llm_api_key", "llm_structured_mode",
    "llm_temperature", "llm_num_ctx",
    "embedding_provider", "embedding_model", "embedding_base_url", "embedding_api_key",
    "merge_threshold",
    "whisper_backend", "whisper_model", "whisper_device", "whisper_compute_type",
    "chunk_minutes", "chunk_overlap_seconds",
}


class ModelSettings(BaseModel):
    llm_provider: str
    llm_model: str
    llm_base_url: str
    llm_api_key: str = ""
    llm_structured_mode: str = "json"
    llm_temperature: float = 0.1
    llm_num_ctx: int = 8192
    embedding_provider: str
    embedding_model: str
    embedding_base_url: str
    embedding_api_key: str = ""
    merge_threshold: float
    whisper_backend: str
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    chunk_minutes: float
    chunk_overlap_seconds: float

    def masked(self) -> dict[str, Any]:
        d = self.model_dump()
        for k in ("llm_api_key", "embedding_api_key"):
            if d.get(k):
                d[k] = "•" * 8 + d[k][-4:]
        return d


_overrides: dict[str, Any] = {}


def load_overrides(stored: dict[str, Any]) -> None:
    _overrides.clear()
    _overrides.update({k: v for k, v in stored.items() if k in EDITABLE_KEYS})


def set_overrides(values: dict[str, Any]) -> dict[str, Any]:
    for k, v in values.items():
        if k not in EDITABLE_KEYS or v is None:
            continue
        # Masked keys sent back unchanged from the UI must not overwrite the secret.
        if k.endswith("api_key") and isinstance(v, str) and v.startswith("•"):
            continue
        _overrides[k] = v
    return dict(_overrides)


def current() -> ModelSettings:
    base = {k: getattr(settings, k) for k in EDITABLE_KEYS}
    base.update(_overrides)
    return ModelSettings(**base)


def get(key: str) -> Any:
    return _overrides.get(key, getattr(settings, key))
