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

        direct, direct_uncertainty = self._direct_score(
            asset, df, direction, strategy, timeframe, entry, stop_loss, target
        )
        foundation, foundation_uncertainty = self._foundation_score(asset, df)
        sentiment = self._sentiment_score(asset)
        has_direct = self._loaded.get("direct") == "local outcome model"
        has_foundation = self._loaded.get("chronos", "").startswith(settings.ai_foundation_model)
        has_sentiment = bool(settings.ai_sentiment_cache and os.path.exists(settings.ai_sentiment_cache))
        if not (has_direct or has_foundation or has_sentiment):
            return EnsembleResult(False, reason="no model output available")
        values = [direct, foundation, sentiment]
        edges = [2.0 * v - 1.0 for v in values]
        weights = self._weights(sentiment)
        edge = float(sum(w * e for w, e in zip(weights, edges)))
        agreement = 1.0 - min(1.0, np.std(edges) / 1.25)
        uncertainty = float(np.average(
            [direct_uncertainty, foundation_uncertainty, 0.65], weights=weights
        ))
        score = float(np.clip(0.5 + 0.5 * edge * agreement * (1.0 - uncertainty), 0.0, 1.0))
        return EnsembleResult(
            available=True, score=score, edge=edge, direct=direct,
            foundation=foundation, sentiment=sentiment, agreement=agreement,
            uncertainty=uncertainty, reason="ensemble evaluated",
            models=dict(self._loaded),
        )

    @staticmethod
    def _weights(sentiment: float) -> tuple[float, float, float]:
        # Keep sentiment small during normal conditions; it is noisy.  Give it
        # more influence only when it is materially directional.
        if abs(sentiment - 0.5) >= 0.18:
            return 0.40, 0.30, 0.30
        return 0.45, 0.35, 0.20

    def _direct_score(self, asset: str, df: pd.DataFrame, direction: str,
                      strategy: str | None, timeframe: str,
                      entry: float | None, stop_loss: float | None,
                      target: float | None) -> tuple[float, float]:
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
                return 0.5, 1.0
            with open(metadata_file, encoding="utf-8") as f:
                if not json.load(f).get("active"):
                    return 0.5, 1.0
            from app.ai_engine.signal_eval import predict_win_probability
            p = predict_win_probability(asset, df, direction, strategy, timeframe,
                                        entry, stop_loss, target)
            self._loaded["direct"] = "local outcome model"
            return float(np.clip(p, 0.0, 1.0)), 0.25
        except Exception as exc:  # noqa: BLE001
            log.warning("Direct model unavailable: %s", exc)
            return 0.5, 1.0

    def _foundation_score(self, asset: str, df: pd.DataFrame) -> tuple[float, float]:
        # Chronos is optional. A native adapter is only attempted when enabled;
        # otherwise no fabricated forecast is allowed into the execution gate.
        model_id = settings.ai_foundation_model
        if not model_id:
            return 0.5, 1.0
        try:
            model = self._load_chronos()
            series = pd.to_numeric(df["close"], errors="coerce").dropna().tail(256)
            if len(series) < 40:
                return 0.5, 1.0
            forecast = model.predict(
                torch.tensor(np.asarray(series, dtype=np.float32)),
                prediction_length=settings.ai_forecast_horizon,
            )
            values = np.asarray(forecast[0])
            median = float(np.median(values[:, -1] if values.ndim > 1 else values))
            last = float(series.iloc[-1])
            p = 0.65 if median > last else 0.35 if median < last else 0.5
            spread = float(np.std(values) / max(abs(last), 1e-9))
            return p, float(np.clip(spread / max(settings.ai_uncertainty_scale, 1e-9), 0.0, 1.0))
        except Exception as exc:  # noqa: BLE001
            log.warning("Foundation model unavailable (%s): %s", model_id, exc)
            self._loaded.pop("chronos", None)
            self._chronos = None
            return 0.5, 1.0

    def _sentiment_score(self, asset: str) -> float:
        # The news route/service can populate a short-lived JSONL/cache later;
        # this adapter reads only the configured local cache and never scrapes
        # or calls a network endpoint inside the order path.
        path = settings.ai_sentiment_cache
        if not path or not os.path.exists(path):
            return 0.5
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
                decay = math.exp(-age / max(settings.ai_sentiment_half_life_seconds, 1.0))
                score = float(row.get("score", 0.0))
                vals.append((score, decay * float(row.get("confidence", 1.0))))
            if not vals:
                return 0.5
            total = sum(w for _, w in vals) or 1.0
            return float(np.clip(0.5 + 0.5 * sum(v * w for v, w in vals) / total, 0.0, 1.0))
        except Exception as exc:  # noqa: BLE001
            log.warning("Sentiment cache unavailable: %s", exc)
            return 0.5


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
