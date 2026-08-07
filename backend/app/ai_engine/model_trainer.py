"""Outcome-based, walk-forward model training and model governance."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone

import joblib
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from app.ai_engine.features import FEATURE_COLS, generate_features
from app.core.logging_setup import get_logger
from app.services.history_store import history_store

log = get_logger("ai_engine.trainer")
MODEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "models"))
MIN_OUTCOME_SAMPLES = 40


def model_path(asset: str) -> str:
    return os.path.join(MODEL_DIR, f"{asset.upper()}_filter.joblib")


def metadata_path(asset: str) -> str:
    return os.path.join(MODEL_DIR, f"{asset.upper()}_filter.meta.json")


def train_asset_from_history(asset: str, min_samples: int = MIN_OUTCOME_SAMPLES) -> dict:
    """Train on realized trade outcomes in chronological walk-forward order."""
    rows = [r for r in history_store.all()
            if (r.get("asset") or "").upper() == asset.upper()
            and r.get("strategy") and r.get("learning_features")
            and r.get("pnl") is not None]
    rows.sort(key=lambda r: r.get("closed_at") or "")
    if len(rows) < min_samples:
        return {"asset": asset, "ok": False, "active": False,
                "reason": "insufficient outcome-labelled trades", "samples": len(rows)}

    data = pd.DataFrame([r["learning_features"] for r in rows]).reindex(columns=FEATURE_COLS)
    labels = pd.Series([1 if float(r.get("pnl", 0.0)) > 0 else 0 for r in rows])
    clean = data.notna().all(axis=1)
    data, labels = data.loc[clean], labels.loc[clean].astype(int)
    if len(data) < min_samples or labels.nunique() < 2:
        return {"asset": asset, "ok": False, "active": False,
                "reason": "insufficient class diversity", "samples": len(data)}

    split = min(max(int(len(data) * 0.75), 25), len(data) - 10)
    X_train, X_test = data.iloc[:split], data.iloc[split:]
    y_train, y_test = labels.iloc[:split], labels.iloc[split:]
    if y_train.nunique() < 2 or y_test.nunique() < 2:
        return {"asset": asset, "ok": False, "active": False,
                "reason": "walk-forward split lacks both classes", "samples": len(data)}

    base = RandomForestClassifier(n_estimators=300, max_depth=7, min_samples_leaf=3,
                                  class_weight="balanced_subsample", random_state=42, n_jobs=-1)
    model = CalibratedClassifierCV(base, cv=3, method="sigmoid")
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)[:, 1]
    baseline_p = float(y_train.mean())
    candidate_logloss = float(log_loss(y_test, proba, labels=[0, 1]))
    baseline_logloss = float(log_loss(y_test, [baseline_p] * len(y_test), labels=[0, 1]))
    auc = float(roc_auc_score(y_test, proba))
    brier = float(brier_score_loss(y_test, proba))
    existing = model_metadata(asset)
    active = candidate_logloss < baseline_logloss and auc >= 0.52
    if active and existing.get("active") and existing.get("validation_logloss"):
        # Champion/challenger guard: do not replace a live model with a weaker
        # candidate just because the rolling validation window changed.
        active = candidate_logloss <= float(existing["validation_logloss"]) * 1.05
    metadata = {
        "model_trained": True, "asset": asset.upper(), "model_type": "outcome_calibrated",
        "feature_version": 2, "feature_cols": FEATURE_COLS, "samples": int(len(data)),
        "train_samples": int(len(X_train)), "validation_samples": int(len(X_test)),
        "validation_auc": round(auc, 4), "validation_logloss": round(candidate_logloss, 4),
        "baseline_logloss": round(baseline_logloss, 4), "brier": round(brier, 4),
        "active": active, "promotion_reason": "validated challenger" if active else "rejected by validation",
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    if active:
        os.makedirs(MODEL_DIR, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=f"{asset}_filter_", suffix=".joblib", dir=MODEL_DIR)
        os.close(fd)
        try:
            joblib.dump({"model": model, "metadata": metadata}, tmp)
            os.replace(tmp, model_path(asset))
            with open(metadata_path(asset), "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        log.info("Promoted outcome model %s: %s", asset, metadata)
    else:
        log.info("Rejected outcome challenger %s: %s", asset, metadata)
    return {"asset": asset, "ok": True, **metadata}


def train_asset(asset: str, df: pd.DataFrame, horizon: int = 5) -> dict:
    """Legacy price-direction bootstrap retained as a fallback utility."""
    if df is None or len(df) < 300:
        return {"asset": asset, "ok": False, "reason": "insufficient data",
                "rows": 0 if df is None else len(df)}
    feats = generate_features(df)
    cols = ["returns", "rsi", "macd_norm", "atr_pct", "mom_10"]
    feats["target"] = (feats["close"].shift(-horizon) > feats["close"]).astype(float)
    feats = feats.dropna(subset=cols + ["target"])
    if len(feats) < 200:
        return {"asset": asset, "ok": False, "reason": "too few clean rows", "rows": len(feats)}
    model = RandomForestClassifier(n_estimators=150, max_depth=5, min_samples_leaf=20,
                                   class_weight="balanced", random_state=42)
    model.fit(feats[cols], feats["target"].astype(int))
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, model_path(asset))
    return {"asset": asset, "ok": True, "model_type": "bootstrap_price_direction",
            "rows": int(len(feats)), "path": model_path(asset)}


def model_metadata(asset: str) -> dict:
    path = metadata_path(asset)
    if not os.path.exists(path):
        rows = [r for r in history_store.all()
                if (r.get("asset") or "").upper() == asset.upper()
                and r.get("strategy") and r.get("learning_features") and r.get("pnl") is not None]
        return {"model_trained": os.path.exists(model_path(asset)), "active": False,
                "model_type": "legacy_bootstrap" if os.path.exists(model_path(asset)) else None,
                "outcome_samples": len(rows)}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"model_trained": os.path.exists(model_path(asset)), "active": False}
