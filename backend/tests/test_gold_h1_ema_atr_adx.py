from __future__ import annotations

import numpy as np
import pandas as pd

from app.strategies.gold_h1_ema_atr_adx import GoldH1EmaAtrAdx
from app.strategies.registry import strategy_scan_lookback, strategy_scan_timeframe


def _frame(periods: int = 500) -> pd.DataFrame:
    index = pd.date_range("2026-01-05 03:00:00", periods=periods, freq="h")
    close = np.linspace(2000.0, 2300.0, periods)
    return pd.DataFrame({
        "open": close - 0.2,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "tick_volume": np.full(periods, 100.0),
    }, index=index)


def test_registry_declares_gold_h1_requirements():
    assert strategy_scan_timeframe("gold_h1_ema_atr_adx") == "H1"
    assert strategy_scan_lookback("gold_h1_ema_atr_adx") == 2000
    strategy = GoldH1EmaAtrAdx()
    assert strategy.target_rr == 2.0
    assert strategy.min_atr_percentile == 20.0


def test_vantage_server_time_is_normalized_to_utc_session():
    strategy = GoldH1EmaAtrAdx(
        session_start_utc=7, session_end_utc=18, server_utc_offset_hours=3,
    )
    assert strategy._in_session(pd.Timestamp("2026-01-05 10:00:00"))
    assert not strategy._in_session(pd.Timestamp("2026-01-05 09:00:00"))
    assert not strategy._in_session(pd.Timestamp("2026-01-10 12:00:00"))


def test_asset_and_timeframe_scope_fail_closed():
    frame = _frame()
    strategy = GoldH1EmaAtrAdx()
    assert all(s is None for s in strategy.signals("BTC", frame, "H1"))
    assert "only trades GOLD" in (strategy.last_reason or "")
    assert all(s is None for s in strategy.signals("GOLD", frame, "M15"))
    assert "requires H1" in (strategy.last_reason or "")


def test_specialization_can_issue_only_during_configured_session():
    frame = _frame()
    strategy = GoldH1EmaAtrAdx(
        fast_ema_length=3, slow_ema_length=8, atr_length=3,
        atr_multiplier=0.1, adx_length=3, adx_smoothing=3,
        adx_threshold=0, long_ema_length=10, long_slope_bars=2,
        min_atr_percentile=0, max_atr_percentile=100,
        session_start_utc=7, session_end_utc=18,
    )
    signals = [
        (frame.index[i], signal)
        for i, signal in enumerate(strategy.signals("GOLD", frame, "H1"))
        if signal is not None
    ]
    assert signals
    assert all(strategy._in_session(timestamp) for timestamp, _ in signals)
