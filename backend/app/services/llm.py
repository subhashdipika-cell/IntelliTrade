"""Shared OpenAI-compatible LLM client.

Provider-aware (OpenRouter cloud or local Ollama, per `settings.llm_provider`).
One place to send a /chat/completions request and to defensively parse JSON out
of a model reply. Used by the Wiki gatekeeper and the Strategy Review.

This module is fail-LOUD (raises on failure); each caller decides how to degrade
(the gatekeeper fails open, the review surfaces the error)."""
from __future__ import annotations

import json
import re

import httpx

from app.core.config import settings
from app.core.logging_setup import get_logger

log = get_logger("services.llm")

_TIMEOUT = 20.0
_LOCAL_TIMEOUT = 120.0  # local models can be slow, especially on longer prompts


def models() -> list[str]:
    """Primary then fallback, skipping any that are unset."""
    return [m for m in (settings.llm_model, settings.llm_model_fallback) if m]


def chat(messages: list[dict], *, temperature: float = 0.0,
         max_tokens: int | None = None, timeout: float | None = None,
         provider: str | None = None, models_override: list[str] | None = None) -> str:
    """Return the first working model's reply text. Raises if all models fail.
    `provider`/`models_override` let one feature use a different backend than the
    global one (e.g. Strategy Review → OpenRouter while the gatekeeper is Ollama)."""
    base_url, key, is_local = settings.llm_endpoint(provider)
    use_models = models_override or models()
    last_exc: Exception | None = None
    for model in use_models:
        if not model:
            continue
        try:
            return _one(model, messages, temperature, max_tokens, timeout,
                        base_url, key, is_local)
        except Exception as exc:  # noqa: BLE001 — try the next model
            log.warning("LLM '%s' failed: %s", model, exc)
            last_exc = exc
    raise RuntimeError(f"all LLM models failed ({last_exc})")


def _one(model: str, messages: list[dict], temperature: float,
         max_tokens: int | None, timeout: float | None,
         base_url: str, key: str, is_local: bool) -> str:
    to = timeout or (_LOCAL_TIMEOUT if is_local else _TIMEOUT)
    payload: dict = {"model": model, "messages": messages, "temperature": temperature}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    resp = httpx.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {key or 'ollama'}",
            "Content-Type": "application/json",
            "X-Title": "IntelliTrade",
        },
        json=payload,
        timeout=to,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def extract_json(content: str):
    """Best-effort parse of a JSON object/array from a model reply (models often
    wrap JSON in prose or code fences). Returns the parsed value or None."""
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}|\[.*\]", content, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
