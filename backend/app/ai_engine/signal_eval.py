"""Live scoring for governed, outcome-trained models."""
from __future__ import annotations

import os
import joblib
import pandas as pd

from app.ai_engine.features import FEATURE_COLS, context_features, generate_features
from app.ai_engine.model_trainer import model_metadata, model_path

_cache: dict[str, object] = {}


def predict_win_probability(asset: str, df: pd.DataFrame, direction: str = "BUY",
                            strategy: str | None = None, timeframe: str = "H1",
                            entry: float | None = None, stop_loss: float | None = None,
                            target: float | None = None) -> float:
    meta = model_metadata(asset)
    if not meta.get("active"):
        return 1.0
    path = model_path(asset)
    if df is None or len(df) < 30 or not os.path.exists(path):
        return 1.0
    market_cols = ["returns", "rsi", "macd_norm", "atr_pct", "mom_10"]
    feats = generate_features(df).dropna(subset=market_cols)
    if feats.empty:
        return 1.0
    risk = abs(float(entry) - float(stop_loss)) if entry is not None and stop_loss is not None else 0.0
    rr = abs(float(target) - float(entry)) / risk if risk and target is not None else 0.0
    row = feats.iloc[[-1]][market_cols].copy()
    for key, value in context_features(direction, rr, strategy, timeframe).items():
        row[key] = value
    row = row.reindex(columns=meta.get("feature_cols", FEATURE_COLS), axis=1)
    model = _load(path)
    proba = model.predict_proba(row)[0]
    classes = list(model.classes_)
    return float(proba[classes.index(1)]) if 1 in classes else 0.0


def _load(path: str):
    model = _cache.get(path)
    mtime = os.path.getmtime(path)
    if model is None or _cache.get(f"{path}::mtime") != mtime:
        payload = joblib.load(path)
        model = payload["model"] if isinstance(payload, dict) and "model" in payload else payload
        _cache[path] = model
        _cache[f"{path}::mtime"] = mtime
    return model


def has_model(asset: str) -> bool:
    return os.path.exists(model_path(asset))
