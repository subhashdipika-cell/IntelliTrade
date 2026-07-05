"""Scores a signal with the trained meta-labeling model.

Returns a win-probability in [0,1] for the signal's DIRECTION:
  - model predicts P(up over next bars);
  - BUY confidence = P(up), SELL confidence = 1 - P(up).
If no model exists for the asset, returns 1.0 (pass-through) so an untrained
system never blocks itself."""
from __future__ import annotations

import os

import joblib
import pandas as pd

from app.ai_engine.features import FEATURE_COLS, generate_features
from app.ai_engine.model_trainer import model_path
from app.core.logging_setup import get_logger

log = get_logger("ai_engine.eval")

_cache: dict[str, object] = {}


def predict_win_probability(asset: str, df: pd.DataFrame, direction: str = "BUY") -> float:
    path = model_path(asset)
    if not os.path.exists(path):
        return 1.0
    if df is None or len(df) < 30:
        return 1.0

    model = _load(path)
    feats = generate_features(df).dropna(subset=FEATURE_COLS)
    if feats.empty:
        return 1.0

    X = feats[FEATURE_COLS].iloc[[-1]]
    proba = model.predict_proba(X)[0]
    classes = list(model.classes_)
    p_up = float(proba[classes.index(1)]) if 1 in classes else 1.0
    return p_up if direction.upper() == "BUY" else 1.0 - p_up


def _load(path: str):
    model = _cache.get(path)
    if model is None or _cache.get(f"{path}::mtime") != os.path.getmtime(path):
        model = joblib.load(path)
        _cache[path] = model
        _cache[f"{path}::mtime"] = os.path.getmtime(path)
    return model


def has_model(asset: str) -> bool:
    return os.path.exists(model_path(asset))
