"""Optional Hugging Face ensemble for autonomous DEMO trade filtering.

The ensemble is deliberately an adapter, not a second trading engine.  It only
scores a signal that already passed a deterministic strategy.  Heavy ML
dependencies are imported lazily so IntelliTrade can still start when the
models are not installed; in blocking mode that condition is treated as a
safe HOLD by the pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import importlib.util
import math
import os
import time
from typing import Any

# Windows compatibility: Torch must initialize before NumPy/Pandas native
# libraries are loaded, otherwise c10.dll can intermittently report 1114.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
try:
    import torch  # type: ignore
    _TORCH_IMPORT_ERROR: Exception | None = None
    try:
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass
except Exception as exc:  # noqa: BLE001
    torch = None  # type: ignore
    _TORCH_IMPORT_ERROR = exc

import numpy as np
import pandas as pd

from app.core.config import settings
from app.core.logging_setup import get_logger

log = get_logger("ai_engine.hf_ensemble")


def _prepare_local_torch() -> None:
    """Preload Torch before Chronos/Transformers on Windows.

    On this machine, importing Chronos first intermittently caused Torch's
    c10.dll to fail with WinError 1114. Preloading Torch and limiting CPU
    threads avoids the DLL/OpenMP initialization race without changing the
    broker or scanner processes.
    """
    if torch is None:
        raise RuntimeError(f"Torch initialization failed: {_TORCH_IMPORT_ERROR}")


@dataclass
class EnsembleResult:
    available: bool
    score: float = 0.5
    edge: float = 0.0
    direct: float = 0.5
    foundation: float = 0.5
    sentiment: float = 0.5
    agreement: float = 0.0
    uncertainty: float = 1.0
    reason: str = ""
    models: dict[str, str] | None = None
    active_models: list[str] | None = None
    weights: dict[str, float] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class HFEnsemble:
    """Lazy, cached adapters for FinBERT and time-series foundation models."""

    def __init__(self) -> None:
        self._sentiment = None
        self._chronos = None
        self._moirai = None
        self._loaded: dict[str, str] = {}

    def readiness(self, deep: bool = False) -> dict[str, Any]:
        """Report local model readiness without making network requests.

        The default check is lightweight (packages + cache + loaded state).
        ``deep=True`` also loads each cached model and runs a tiny local smoke
        inference. It may take several seconds on the first CPU invocation.
        """
        torch_ready = torch is not None
        chronos_package = importlib.util.find_spec("chronos") is not None
        chronos_cached = _model_cached(settings.ai_foundation_model)
        chronos_error: str | None = None
        chronos_inference = False

        if deep and torch_ready and chronos_package and chronos_cached:
            try:
                model = self._load_chronos()
                forecast = model.predict(
                    torch.linspace(100.0, 101.0, 64), prediction_length=1
                )
                chronos_inference = bool(getattr(forecast, "numel", lambda: 0)())
            except Exception as exc:  # noqa: BLE001
                chronos_error = str(exc)

        from app.ai_engine.sentiment_service import sentiment_readiness
        finbert = sentiment_readiness(deep=deep)
        chronos_loaded = self._chronos is not None
        chronos_ready = (
            torch_ready and chronos_package and chronos_cached
            and (not deep or chronos_inference)
        )
        execution_ready = settings.ai_ensemble_enabled and chronos_ready
        return {
            "ready": execution_ready,
            "all_models_ready": execution_ready and bool(finbert["ready"]),
            "mode": "local",
            "local_only": settings.ai_model_local_only,
            "blocking": settings.ai_ensemble_blocking,
            "deep_check": deep,
            "torch": {
                "ready": torch_ready,
                "version": getattr(torch, "__version__", None),
                "error": None if torch_ready else str(_TORCH_IMPORT_ERROR),
            },
            "chronos": {
                "ready": chronos_ready,
                "package_installed": chronos_package,
                "model_id": settings.ai_foundation_model,
                "cached": chronos_cached,
                "loaded": chronos_loaded,
                "inference_ok": chronos_inference if deep else None,
                "error": chronos_error,
            },
            "finbert": finbert,
        }

    def _load_chronos(self):
        _prepare_local_torch()
        if self._chronos is None:
            from chronos import ChronosPipeline  # type: ignore
            self._chronos = ChronosPipeline.from_pretrained(
                settings.ai_foundation_model,
                device_map="auto",
                torch_dtype="auto",
                local_files_only=settings.ai_model_local_only,
            )
            self._loaded["chronos"] = settings.ai_foundation_model
        return self._chronos

    def evaluate(self, asset: str, df: pd.DataFrame, direction: str,
                 strategy: str | None, timeframe: str,
                 entry: float | None, stop_loss: float | None,
                 target: float | None) -> EnsembleResult:
        if not settings.ai_ensemble_enabled:
            return EnsembleResult(False, reason="AI ensemble disabled")
        if df is None or len(df) < settings.ai_min_bars:
            return EnsembleResult(False, reason="insufficient closed bars")

        direct, direct_uncertainty, has_direct = self._direct_score(
            asset, df, direction, strategy, timeframe, entry, stop_loss, target
        )
        foundation, foundation_uncertainty, has_foundation = self._foundation_score(
            asset, df, direction
        )
        sentiment, sentiment_uncertainty, has_sentiment = self._sentiment_score(
            asset, direction
        )
        signals = {
            "direct": (direct, direct_uncertainty, has_direct),
            "foundation": (foundation, foundation_uncertainty, has_foundation),
            "sentiment": (sentiment, sentiment_uncertainty, has_sentiment),
        }
        # Sentiment is corroboration, never the sole authority for execution.
        if not (has_direct or has_foundation):
            return EnsembleResult(False, reason="no model output available")
        score, edge, agreement, uncertainty, weights = _combine_signals(signals)
        return EnsembleResult(
            available=True, score=score, edge=edge, direct=direct,
            foundation=foundation, sentiment=sentiment, agreement=agreement,
            uncertainty=uncertainty, reason="ensemble evaluated",
            models=dict(self._loaded),
            active_models=list(weights), weights=weights,
        )

    def _direct_score(self, asset: str, df: pd.DataFrame, direction: str,
                      strategy: str | None, timeframe: str,
                      entry: float | None, stop_loss: float | None,
                      target: float | None) -> tuple[float, float, bool]:
        # Existing calibrated outcome model is the first direct signal.  It is
        # broker/strategy-specific and therefore safer than a generic HF model.
        try:
            # Avoid importing sklearn/joblib on every scanner cycle when no
            # promoted model exists. The metadata file is the promotion record.
            import json
            model_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "models"))
            model_file = os.path.join(model_dir, f"{asset.upper()}_filter.joblib")
            metadata_file = os.path.join(model_dir, f"{asset.upper()}_filter.meta.json")
            if not os.path.exists(model_file) or not os.path.exists(metadata_file):
                return 0.5, 1.0, False
            with open(metadata_file, encoding="utf-8") as f:
                if not json.load(f).get("active"):
                    return 0.5, 1.0, False
            from app.ai_engine.signal_eval import predict_win_probability
            p = predict_win_probability(asset, df, direction, strategy, timeframe,
                                        entry, stop_loss, target)
            self._loaded["direct"] = "local outcome model"
            return float(np.clip(p, 0.0, 1.0)), 0.25, True
        except Exception as exc:  # noqa: BLE001
            log.warning("Direct model unavailable: %s", exc)
            self._loaded.pop("direct", None)
            return 0.5, 1.0, False

    def _foundation_score(self, asset: str, df: pd.DataFrame,
                          direction: str) -> tuple[float, float, bool]:
        # Chronos is optional. A native adapter is only attempted when enabled;
        # otherwise no fabricated forecast is allowed into the execution gate.
        model_id = settings.ai_foundation_model
        if not model_id:
            return 0.5, 1.0, False
        try:
            model = self._load_chronos()
            series = pd.to_numeric(df["close"], errors="coerce").dropna().tail(256)
            if len(series) < 40:
                return 0.5, 1.0, False
            forecast = model.predict(
                torch.tensor(np.asarray(series, dtype=np.float32)),
                prediction_length=settings.ai_forecast_horizon,
            )
            values = np.asarray(forecast[0])
            terminal = values[:, -1] if values.ndim > 1 else values
            last = float(series.iloc[-1])
            p_up = float(np.mean(terminal > last) + 0.5 * np.mean(terminal == last))
            # Keep a small calibration guard against overconfident 20-sample
            # forecasts, then map market direction to the proposed trade.
            p_up = float(np.clip(p_up, 0.20, 0.80))
            p = _for_trade_direction(p_up, direction)
            spread = float(np.std(values) / max(abs(last), 1e-9))
            directional_uncertainty = 1.0 - abs(2.0 * p_up - 1.0)
            spread_floor = 0.25 * float(np.clip(
                spread / max(settings.ai_uncertainty_scale, 1e-9), 0.0, 1.0
            ))
            uncertainty = max(directional_uncertainty, spread_floor)
            return p, uncertainty, True
        except Exception as exc:  # noqa: BLE001
            log.warning("Foundation model unavailable (%s): %s", model_id, exc)
            self._loaded.pop("chronos", None)
            self._chronos = None
            return 0.5, 1.0, False

    def _sentiment_score(self, asset: str,
                         direction: str) -> tuple[float, float, bool]:
        # The news route/service can populate a short-lived JSONL/cache later;
        # this adapter reads only the configured local cache and never scrapes
        # or calls a network endpoint inside the order path.
        path = settings.ai_sentiment_cache
        if not path or not os.path.exists(path):
            return 0.5, 1.0, False
        try:
            import json
            with open(path, encoding="utf-8") as f:
                rows = json.load(f)
            now = time.time()
            vals: list[tuple[float, float]] = []
            for row in rows if isinstance(rows, list) else []:
                if str(row.get("asset", "")).upper() not in {asset.upper(), "MACRO"}:
                    continue
                age = max(0.0, now - float(row.get("timestamp", now)))
                if age > 4.0 * settings.ai_sentiment_half_life_seconds:
                    continue
                decay = math.exp(-age / max(settings.ai_sentiment_half_life_seconds, 1.0))
                score = float(row.get("score", 0.0))
                vals.append((score, decay * float(row.get("confidence", 1.0))))
            if not vals:
                return 0.5, 1.0, False
            total = sum(w for _, w in vals) or 1.0
            market_p = float(np.clip(
                0.5 + 0.5 * sum(v * w for v, w in vals) / total, 0.0, 1.0
            ))
            confidence = min(1.0, total / max(len(vals), 1))
            return _for_trade_direction(market_p, direction), 1.0 - confidence, True
        except Exception as exc:  # noqa: BLE001
            log.warning("Sentiment cache unavailable: %s", exc)
            return 0.5, 1.0, False


_BASE_WEIGHTS = {"direct": 0.45, "foundation": 0.35, "sentiment": 0.20}


def _for_trade_direction(p_up: float, direction: str) -> float:
    """Convert a market-up probability into support for BUY or SELL."""
    p = float(np.clip(p_up, 0.0, 1.0))
    return 1.0 - p if direction.upper() == "SELL" else p


def _combine_signals(
    signals: dict[str, tuple[float, float, bool]],
) -> tuple[float, float, float, float, dict[str, float]]:
    """Combine only available model outputs and renormalize their weights."""
    active = {name: value for name, value in signals.items() if value[2]}
    raw_total = sum(_BASE_WEIGHTS[name] for name in active)
    if not active or raw_total <= 0:
        return 0.5, 0.0, 0.0, 1.0, {}
    weights = {name: _BASE_WEIGHTS[name] / raw_total for name in active}
    probability = float(sum(weights[name] * active[name][0] for name in active))
    uncertainty = float(sum(
        weights[name] * float(np.clip(active[name][1], 0.0, 1.0))
        for name in active
    ))
    edges = np.asarray([2.0 * active[name][0] - 1.0 for name in active], dtype=float)
    agreement = 1.0 if len(edges) == 1 else float(
        1.0 - min(1.0, float(np.std(edges)) / 1.25)
    )
    edge = 2.0 * probability - 1.0
    # Uncertainty moderates conviction but does not inject a neutral/missing
    # model into the vote. This allows one strong available model to validate
    # a strategy while retaining a conservative confidence haircut.
    quality = 1.0 - 0.5 * uncertainty
    score = float(np.clip(
        0.5 + (probability - 0.5) * agreement * quality, 0.0, 1.0
    ))
    return score, edge, agreement, uncertainty, weights


_BASE_WEIGHTS = {"direct": 0.45, "foundation": 0.35, "sentiment": 0.20}


def _for_trade_direction(p_up: float, direction: str) -> float:
    """Convert a market-up probability into support for BUY or SELL."""
    p = float(np.clip(p_up, 0.0, 1.0))
    return 1.0 - p if direction.upper() == "SELL" else p


def _combine_signals(
    signals: dict[str, tuple[float, float, bool]],
) -> tuple[float, float, float, float, dict[str, float]]:
    """Combine only available model outputs and renormalize their weights."""
    active = {name: value for name, value in signals.items() if value[2]}
    raw_total = sum(_BASE_WEIGHTS[name] for name in active)
    if not active or raw_total <= 0:
        return 0.5, 0.0, 0.0, 1.0, {}
    weights = {name: _BASE_WEIGHTS[name] / raw_total for name in active}
    probability = float(sum(weights[name] * active[name][0] for name in active))
    uncertainty = float(sum(
        weights[name] * float(np.clip(active[name][1], 0.0, 1.0))
        for name in active
    ))
    edges = np.asarray([2.0 * active[name][0] - 1.0 for name in active], dtype=float)
    agreement = 1.0 if len(edges) == 1 else float(
        1.0 - min(1.0, float(np.std(edges)) / 1.25)
    )
    edge = 2.0 * probability - 1.0
    # Uncertainty moderates conviction but does not inject a neutral/missing
    # model into the vote. This allows one strong available model to validate
    # a strategy while retaining a conservative confidence haircut.
    quality = 1.0 - 0.5 * uncertainty
    score = float(np.clip(
        0.5 + (probability - 0.5) * agreement * quality, 0.0, 1.0
    ))
    return score, edge, agreement, uncertainty, weights


_ensemble = HFEnsemble()


def _model_cached(model_id: str) -> bool:
    if not model_id:
        return False
    try:
        from huggingface_hub import try_to_load_from_cache
        path = try_to_load_from_cache(model_id, "config.json")
        return isinstance(path, str) and os.path.exists(path)
    except Exception:  # noqa: BLE001
        return False


def evaluate_ensemble(*args, **kwargs) -> EnsembleResult:
    return _ensemble.evaluate(*args, **kwargs)


def ai_readiness(deep: bool = False) -> dict[str, Any]:
    return _ensemble.readiness(deep=deep)
