"""Trains the per-asset meta-labeling filter.

Bootstrap target: did price rise over the next `horizon` bars? This makes the
filter functional from day one using price history. The intended end-state is to
retrain on REAL closed-trade outcomes from the History store (label = was the
executed signal a winner?) once enough trades exist — same FEATURE_COLS, just a
different y. Swap the labelling in `_label` when you're ready."""
from __future__ import annotations

import os

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from app.ai_engine.features import FEATURE_COLS, generate_features
from app.core.logging_setup import get_logger

log = get_logger("ai_engine.trainer")

MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "models"))


def model_path(asset: str) -> str:
    return os.path.join(MODEL_DIR, f"{asset.upper()}_filter.joblib")


def train_asset(asset: str, df: pd.DataFrame, horizon: int = 5) -> dict:
    if df is None or len(df) < 300:
        return {"asset": asset, "ok": False, "reason": "insufficient data",
                "rows": 0 if df is None else len(df)}

    feats = generate_features(df)
    feats["target"] = _label(feats, horizon)
    feats = feats.dropna(subset=FEATURE_COLS + ["target"])
    if len(feats) < 200:
        return {"asset": asset, "ok": False, "reason": "too few clean rows",
                "rows": len(feats)}

    X, y = feats[FEATURE_COLS], feats["target"].astype(int)
    model = RandomForestClassifier(
        n_estimators=150, max_depth=5, min_samples_leaf=20,
        class_weight="balanced", random_state=42,
    )
    model.fit(X, y)

    os.makedirs(MODEL_DIR, exist_ok=True)
    path = model_path(asset)
    joblib.dump(model, path)
    log.info("Trained %s filter on %d rows -> %s", asset, len(feats), path)
    return {
        "asset": asset, "ok": True, "rows": int(len(feats)),
        "train_accuracy": round(float(model.score(X, y)), 3),  # in-sample, optimistic
        "positive_rate": round(float(y.mean()), 3),
        "path": path,
    }


def _label(feats: pd.DataFrame, horizon: int) -> pd.Series:
    """Bootstrap label: 1 if price is higher `horizon` bars later."""
    return (feats["close"].shift(-horizon) > feats["close"]).astype(float)
