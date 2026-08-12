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


def score_text(text: str, asset: str = "MACRO", source: str = "manual") -> dict[str, Any]:
    """Score one headline with ProsusAI/finbert and append a compact cache row."""
    global _classifier
    if not text.strip():
        raise ValueError("text is required")
    try:
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
        raw = _classifier(text[:2000])
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
