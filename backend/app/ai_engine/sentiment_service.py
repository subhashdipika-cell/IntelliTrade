"""Optional FinBERT headline scorer and local cache writer."""
from __future__ import annotations

import json
import os
import time
from threading import Lock
from typing import Any

from app.core.config import settings
from app.core.logging_setup import get_logger

log = get_logger("ai_engine.sentiment")
_lock = Lock()
_classifier = None


def _load_classifier():
    global _classifier
    if _classifier is None:
        from app.ai_engine.hf_ensemble import _prepare_local_torch
        _prepare_local_torch()
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        from transformers import pipeline
        tokenizer = AutoTokenizer.from_pretrained(
            settings.ai_sentiment_model,
            local_files_only=settings.ai_model_local_only,
        )
        model = AutoModelForSequenceClassification.from_pretrained(
            settings.ai_sentiment_model,
            local_files_only=settings.ai_model_local_only,
        )
        _classifier = pipeline(
            "text-classification", model=model, tokenizer=tokenizer, top_k=None,
        )
    return _classifier


def sentiment_readiness(deep: bool = False) -> dict[str, Any]:
    """Report FinBERT package/cache readiness and optionally test inference."""
    import importlib.util
    package = importlib.util.find_spec("transformers") is not None
    cached = False
    try:
        from huggingface_hub import try_to_load_from_cache
        path = try_to_load_from_cache(settings.ai_sentiment_model, "config.json")
        cached = isinstance(path, str) and os.path.exists(path)
    except Exception:  # noqa: BLE001
        pass
    error: str | None = None
    inference_ok = False
    if deep and package and cached:
        try:
            result = _load_classifier()("Markets are stable.")
            inference_ok = bool(result)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
    ready = package and cached and (not deep or inference_ok)
    return {
        "ready": ready,
        "package_installed": package,
        "model_id": settings.ai_sentiment_model,
        "cached": cached,
        "loaded": _classifier is not None,
        "inference_ok": inference_ok if deep else None,
        "error": error,
    }


def score_text(text: str, asset: str = "MACRO", source: str = "manual") -> dict[str, Any]:
    """Score one headline with ProsusAI/finbert and append a compact cache row."""
    if not text.strip():
        raise ValueError("text is required")
    try:
        raw = _load_classifier()(text[:2000])
        labels = raw[0] if raw and isinstance(raw[0], list) else raw
        probs = {str(x["label"]).lower(): float(x["score"]) for x in labels}
        positive = probs.get("positive", 0.0)
        negative = probs.get("negative", 0.0)
        neutral = probs.get("neutral", 0.0)
        row = {
            "timestamp": time.time(), "asset": asset.upper(), "source": source,
            "score": positive - negative, "confidence": 1.0 - neutral,
            "positive": positive, "negative": negative, "neutral": neutral,
            "text_hash": __import__("hashlib").sha256(text.encode()).hexdigest(),
        }
        _append(row)
        return row
    except ImportError as exc:
        raise RuntimeError("Install transformers and torch before using FinBERT") from exc


def _append(row: dict[str, Any]) -> None:
    path = settings.ai_sentiment_cache
    if not path:
        raise RuntimeError("AI_SENTIMENT_CACHE is not configured")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with _lock:
        rows: list[dict[str, Any]] = []
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    rows = json.load(f)
            except (OSError, json.JSONDecodeError):
                rows = []
        rows = [r for r in rows if r.get("text_hash") != row["text_hash"]]
        rows.append(row)
        rows = rows[-1000:]
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f)
        os.replace(tmp, path)
