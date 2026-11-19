"""Model-agnostic configuration.

Everything is read from environment variables prefixed with ``VID2GRAPH_`` (or a
``.env`` file in the repo root / backend dir). Runtime overrides saved from the UI's
settings modal are layered on top by :mod:`app.core.runtime_settings`.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["ollama", "lmstudio", "vllm", "openai", "anthropic", "gemini", "groq", "openrouter", "deepseek",
                   "openai_compatible", "mock"]
EmbeddingProvider = Literal["auto", "ollama", "sentence-transformers", "openai", "hash"]
WhisperBackend = Literal["auto", "faster-whisper", "mlx", "whisper.cpp", "none"]

_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VID2GRAPH_",
        env_file=[str(_ROOT / ".env"), str(_ROOT / "backend" / ".env")],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    llm_provider: Provider = "ollama"
    llm_model: str = "qwen2.5:7b"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: str = ""
    llm_structured_mode: Literal["json", "tools", "md_json"] = "json"
    llm_temperature: float = 0.1
    llm_max_retries: int = 2
    llm_timeout: int = 180
    llm_num_ctx: int = 8192  # context window hint for Ollama

    # Embeddings
    embedding_provider: EmbeddingProvider = "auto"
    embedding_model: str = "nomic-embed-text"
    embedding_base_url: str = "http://localhost:11434"
    embedding_api_key: str = ""
    merge_threshold: float = 0.85

    # Whisper
    whisper_backend: WhisperBackend = "auto"
    whisper_model: str = "base"
    whisper_device: Literal["auto", "cuda", "cpu"] = "auto"
    whisper_compute_type: Literal["auto", "int8", "float16", "float32"] = "auto"
    whisper_cpp_bin: str = "whisper-cli"
    whisper_cpp_model: str = ""

    # Chunking
    chunk_minutes: float = Field(default=6, ge=1, le=15)
    chunk_overlap_seconds: float = Field(default=45, ge=0, le=300)
    max_chunks_parallel: int = 2

    # Storage / server
    data_dir: Path = Path("./data")
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    seed_demo: bool = True
    demo_media_url: str = ""
    log_level: str = "INFO"

    # ── derived helpers ──────────────────────────────────────────────────────
    @property
    def resolved_data_dir(self) -> Path:
        p = self.data_dir
        if not p.is_absolute():
            p = (_ROOT / p).resolve()
        p.mkdir(parents=True, exist_ok=True)
        (p / "media").mkdir(exist_ok=True)
        (p / "tmp").mkdir(exist_ok=True)
        return p

    @property
    def db_path(self) -> Path:
        return self.resolved_data_dir / "vid2graph.sqlite3"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

# LiteLLM is chatty; keep it quiet unless debugging.
os.environ.setdefault("LITELLM_LOG", "ERROR")
