"""Provider-agnostic LLM client.

* **LiteLLM** gives one ``completion()`` for Ollama, LM Studio, vLLM, OpenAI, …
* **Instructor** turns a Pydantic model into a validated structured response with
  automatic retries (we default to JSON mode — the most reliable for 7B-14B models).
* If Instructor still fails we fall back to a plain completion and lenient JSON
  extraction so a slightly chatty model never kills a whole pipeline run.
* A ``mock`` provider powers tests and a no-model demo.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.core import runtime_settings
from app.core.runtime_settings import ModelSettings

log = logging.getLogger("vid2graph.llm")
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


def _extract_json(text: str) -> Any:
    """Pull the first JSON object/array out of possibly-chatty model output."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    raise LLMError(f"No JSON found in model output: {text[:200]!r}")


def _coerce(model: Type[T], data: Any) -> T:
    """Validate, tolerating a bare list when the model has exactly one list field."""
    if isinstance(data, list):
        list_fields = [k for k, f in model.model_fields.items()
                       if "list" in str(f.annotation).lower()]
        if len(list_fields) == 1:
            data = {list_fields[0]: data}
    return model.model_validate(data)


# provider -> LiteLLM model prefix for hosted APIs that only need an API key
HOSTED_PREFIX = {"anthropic": "anthropic/", "gemini": "gemini/", "groq": "groq/", "deepseek": "deepseek/", "openrouter": "openrouter/"}


class LLMClient:
    def __init__(self, ms: Optional[ModelSettings] = None):
        self.ms = ms or runtime_settings.current()
        self.provider = self.ms.llm_provider
        self.model, self.kwargs = self._resolve()
        self._instructor = None

    # ── provider resolution ──────────────────────────────────────────────────
    def _resolve(self) -> tuple[str, dict[str, Any]]:
        ms = self.ms
        base = ms.llm_base_url.rstrip("/")
        p = ms.llm_provider
        if p == "mock":
            return "mock", {}
        if p == "ollama":
            if base.endswith("/v1"):
                base = base[:-3]
            return f"ollama_chat/{ms.llm_model}", {"api_base": base}
        if p in ("lmstudio", "vllm", "openai_compatible"):
            if not base.endswith("/v1"):
                base += "/v1"
            return f"openai/{ms.llm_model}", {"api_base": base, "api_key": ms.llm_api_key or "sk-local"}
        if p == "openai":
            kw: dict[str, Any] = {"api_key": ms.llm_api_key}
            if base and "openai.com" not in base and base != "http://localhost:11434":
                kw["api_base"] = base if base.endswith("/v1") else base + "/v1"
            model = ms.llm_model if "/" in ms.llm_model else f"openai/{ms.llm_model}"
            return model, kw
        if p in HOSTED_PREFIX:
            # Hosted APIs: LiteLLM knows their endpoints, so only the key (and model) are needed.
            model = ms.llm_model if ms.llm_model.startswith(HOSTED_PREFIX[p]) else f"{HOSTED_PREFIX[p]}{ms.llm_model}"
            return model, {"api_key": ms.llm_api_key}
        raise LLMError(f"Unknown provider {p}")

    @property
    def describe(self) -> str:
        return f"{self.provider}:{self.ms.llm_model}"

    def _common_kwargs(self) -> dict[str, Any]:
        kw = dict(self.kwargs)
        kw["temperature"] = self.ms.llm_temperature
        kw["timeout"] = runtime_settings.get("llm_timeout")
        if self.provider == "ollama":
            kw["num_ctx"] = self.ms.llm_num_ctx
        return kw

    # ── structured ───────────────────────────────────────────────────────────
    def structured(self, response_model: Type[T], system: str, user: str,
                   max_retries: Optional[int] = None) -> T:
        if self.provider == "mock":
            from app.core.mock_llm import mock_structured
            return mock_structured(response_model, system, user)

        import instructor
        import litellm

        retries = runtime_settings.get("llm_max_retries") if max_retries is None else max_retries
        mode = {
            "json": instructor.Mode.JSON,
            "tools": instructor.Mode.TOOLS,
            "md_json": instructor.Mode.MD_JSON,
        }[self.ms.llm_structured_mode]
        if self._instructor is None:
            self._instructor = instructor.from_litellm(litellm.completion, mode=mode)

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        t0 = time.time()
        try:
            result = self._instructor.chat.completions.create(
                model=self.model, messages=messages, response_model=response_model,
                max_retries=retries, **self._common_kwargs(),
            )
            log.debug("structured %s ok in %.1fs", response_model.__name__, time.time() - t0)
            return result
        except Exception as exc:  # noqa: BLE001 — we try one lenient fallback
            log.warning("instructor failed for %s (%s); trying lenient JSON fallback",
                        response_model.__name__, type(exc).__name__)
            return self._structured_fallback(response_model, system, user, exc)

    def _structured_fallback(self, response_model: Type[T], system: str, user: str, cause: Exception) -> T:
        import litellm

        schema = json.dumps(response_model.model_json_schema(), indent=0)
        sys2 = (f"{system}\n\nRespond ONLY with a single JSON object matching this JSON schema "
                f"(no prose, no markdown):\n{schema}")
        try:
            resp = litellm.completion(
                model=self.model,
                messages=[{"role": "system", "content": sys2}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                **self._common_kwargs(),
            )
            text = resp.choices[0].message.content or ""
            return _coerce(response_model, _extract_json(text))
        except (ValidationError, LLMError) as exc2:
            raise LLMError(f"Model output could not be parsed as {response_model.__name__}: {exc2}") from cause
        except Exception as exc2:  # noqa: BLE001
            raise LLMError(f"LLM call failed ({self.describe}): {exc2}") from cause

    # ── free text ────────────────────────────────────────────────────────────
    def complete(self, system: str, user: str, history: Optional[list[dict[str, str]]] = None) -> str:
        if self.provider == "mock":
            from app.core.mock_llm import mock_complete
            return mock_complete(system, user)
        import litellm

        messages = [{"role": "system", "content": system}]
        messages += history or []
        messages.append({"role": "user", "content": user})
        try:
            resp = litellm.completion(model=self.model, messages=messages, **self._common_kwargs())
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"LLM call failed ({self.describe}): {exc}") from exc
        return (resp.choices[0].message.content or "").strip()

    # ── connectivity probe ───────────────────────────────────────────────────
    def probe(self) -> dict[str, Any]:
        """Cheap reachability check used by /api/health and the settings modal."""
        info: dict[str, Any] = {"provider": self.provider, "model": self.ms.llm_model,
                                "base_url": self.ms.llm_base_url, "reachable": False, "detail": ""}
        if self.provider == "mock":
            info.update(reachable=True, detail="mock provider (no model needed)")
            return info
        import httpx
        base = self.ms.llm_base_url.rstrip("/")
        try:
            if self.provider == "ollama":
                r = httpx.get(f"{base.removesuffix('/v1')}/api/tags", timeout=3)
                names = [m.get("name") for m in r.json().get("models", [])]
                info["available_models"] = names
                has = any(n == self.ms.llm_model or n.split(":")[0] == self.ms.llm_model.split(":")[0] for n in names)
                info.update(reachable=True, detail="model pulled" if has else
                            f"Ollama reachable but '{self.ms.llm_model}' not pulled — run: ollama pull {self.ms.llm_model}")
                info["model_available"] = has
            elif self.provider == "openai" or self.provider in HOSTED_PREFIX:
                info.update(reachable=bool(self.ms.llm_api_key), detail="api key set" if self.ms.llm_api_key else "missing API key")
            else:
                url = base if base.endswith("/v1") else base + "/v1"
                headers = {"Authorization": f"Bearer {self.ms.llm_api_key or 'sk-local'}"}
                r = httpx.get(f"{url}/models", timeout=3, headers=headers)
                names = [m.get("id") for m in r.json().get("data", [])]
                info["available_models"] = names
                info.update(reachable=True, detail="endpoint reachable")
        except Exception as exc:  # noqa: BLE001
            info["detail"] = f"unreachable: {type(exc).__name__}"
        return info


def get_llm() -> LLMClient:
    return LLMClient(runtime_settings.current())
