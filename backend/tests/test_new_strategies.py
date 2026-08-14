from __future__ import annotations

import pandas as pd

from app.strategies.btc_volatility_break_retest import BtcVolatilityBreakRetest
from app.strategies.gold_session_break_retest import GoldSessionBreakRetest
from app.strategies.registry import strategy_scan_lookback, strategy_scan_timeframe


def test_new_strategies_are_registered_with_explicit_live_requirements():
    assert strategy_scan_timeframe("gold_session_break_retest") == "M15"
    assert strategy_scan_lookback("gold_session_break_retest") == 1600
    assert strategy_scan_timeframe("btc_volatility_break_retest") == "H1"
    assert strategy_scan_lookback("btc_volatility_break_retest") == 1400


def test_gold_overlap_handles_vantage_server_time_and_dst():
    strategy = GoldSessionBreakRetest(server_utc_offset_hours=3)
    # 16:00 Vantage server time in July = 13:00 UTC, inside the overlap.
    assert strategy._in_overlap(pd.Timestamp("2026-07-06 16:00:00"))
    # 12:00 Vantage server time in July = 09:00 UTC, outside the overlap.
    assert not strategy._in_overlap(pd.Timestamp("2026-07-06 12:00:00"))


def test_btc_weekend_guard_handles_vantage_server_time():
    strategy = BtcVolatilityBreakRetest(server_utc_offset_hours=3)
    # Saturday server time is Friday 22:00 UTC: weekend entries are blocked.
    assert not strategy._weekday_session(pd.Timestamp("2026-06-20 01:00:00"))
    # Monday server time is Sunday 21:00 UTC: entries may resume.
    assert strategy._weekday_session(pd.Timestamp("2026-06-22 00:00:00"))


def test_asset_scoping_and_signal_shape_are_safe():
    index = pd.date_range("2026-07-01", periods=80, freq="h")
    close = pd.Series(range(100, 180), index=index, dtype=float)
    frame = pd.DataFrame({
        "open": close - 0.25,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "tick_volume": 100,
    })
    gold = GoldSessionBreakRetest().signals("BTC", frame, "M15")
    btc = BtcVolatilityBreakRetest().signals("GOLD", frame, "H1")
    assert len(gold) == len(frame)
    assert len(btc) == len(frame)
    assert all(signal is None for signal in gold)
    assert all(signal is None for signal in btc)


def test_empty_input_returns_empty_signal_series():
    assert BtcVolatilityBreakRetest().signals("BTC", pd.DataFrame(), "H1") == []
