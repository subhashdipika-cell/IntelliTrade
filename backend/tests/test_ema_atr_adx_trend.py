from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction
from app.strategies.ema_atr_adx_trend import EmaAtrAdxTrend
from app.strategies.registry import build_strategy, list_strategies


def _frame(close_values: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    close = np.asarray(close_values, dtype=float)
    volume = volumes or [100.0] * len(close)
    return pd.DataFrame({
        "open": close - 0.2,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "tick_volume": volume,
    }, index=pd.date_range("2026-01-01", periods=len(close), freq="h"))


def test_registered_and_parameters_are_constructible():
    assert "ema_atr_adx_trend" in list_strategies()
    strategy = build_strategy("ema_atr_adx_trend", {
        "fast_ema_length": 5.0,
        "slow_ema_length": 12.0,
        "target_rr": 1.5,
    })
    assert isinstance(strategy, EmaAtrAdxTrend)
    assert strategy.fast_ema_length == 5
    assert strategy.slow_ema_length == 12
    assert strategy.target_rr == 1.5


def test_one_signal_only_per_ema_trend_cycle():
    # Low thresholds isolate the Pine state-machine behavior from filter tuning.
    frame = _frame(list(np.linspace(100, 160, 100)))
    strategy = EmaAtrAdxTrend(
        fast_ema_length=3, slow_ema_length=8, atr_length=3,
        atr_multiplier=0.1, adx_length=3, adx_smoothing=3,
        adx_threshold=0, volume_length=3,
    )
    signals = [s for s in strategy.signals("BTC", frame, "H1") if s is not None]
    assert len(signals) == 1
    assert signals[0].direction is Direction.BUY


def test_target_rr_uses_pine_atr_stop_distance():
    frame = _frame(list(np.linspace(100, 160, 100)))
    strategy = EmaAtrAdxTrend(
        fast_ema_length=3, slow_ema_length=8, atr_length=3,
        atr_multiplier=0.1, sl_atr_multiple=1.5, target_rr=2.5,
        adx_length=3, adx_smoothing=3, adx_threshold=0, volume_length=3,
    )
    signal = next(s for s in strategy.signals("GOLD", frame, "H1") if s is not None)
    risk = abs(signal.entry - signal.stop_loss)
    reward = abs(signal.target - signal.entry)
    assert abs(reward / risk - 2.5) < 1e-4


def test_high_volume_confirmation_is_buy_only_like_pine():
    close = [100.0] * 40 + [100.2 + i * 0.05 for i in range(20)]
    volumes = [100.0] * 59 + [1000.0]
    frame = _frame(close, volumes)
    strategy = EmaAtrAdxTrend(
        fast_ema_length=3, slow_ema_length=8, atr_length=3,
        atr_multiplier=100, adx_length=3, adx_smoothing=3,
        adx_threshold=0, volume_length=5, volume_multiplier=1.5,
    )
    signals = [s for s in strategy.signals("ETH", frame, "H1") if s is not None]
    assert len(signals) == 1
    assert signals[0].direction is Direction.BUY


def test_empty_input_is_safe():
    strategy = EmaAtrAdxTrend()
    assert strategy.signals("BTC", pd.DataFrame(), "H1") == []
    assert "Insufficient history" in (strategy.last_reason or "")
