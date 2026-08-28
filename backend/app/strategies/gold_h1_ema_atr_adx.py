"""Gold-only H1 specialization of EMA ATR ADX Trend Signals.

Adds three causal filters before the Pine signal can consume its one-per-trend
state: liquid UTC session, long-EMA direction, and ATR-percentile regime.
"""
from __future__ import annotations

from datetime import timedelta, timezone

import numpy as np
import pandas as pd

from app.strategies.ema_atr_adx_trend import EmaAtrAdxTrend


class GoldH1EmaAtrAdx(EmaAtrAdxTrend):
    name = "Gold H1 EMA ATR ADX"
    scan_timeframe = "H1"
    scan_lookback = 2000

    def __init__(
        self,
        fast_ema_length: int = 9,
        slow_ema_length: int = 21,
        atr_length: int = 14,
        atr_multiplier: float = 1.5,
        sl_atr_multiple: float = 1.5,
        target_rr: float = 2.0,
        adx_length: int = 14,
        adx_smoothing: int = 14,
        adx_threshold: float = 20.0,
        use_high_volume_buy: bool = True,
        volume_length: int = 20,
        volume_multiplier: float = 1.5,
        long_ema_length: int = 100,
        long_slope_bars: int = 5,
        min_atr_percentile: float = 20.0,
        max_atr_percentile: float = 95.0,
        session_start_utc: int = 7,
        session_end_utc: int = 18,
        server_utc_offset_hours: float = 3.0,
    ) -> None:
        super().__init__(
            fast_ema_length=fast_ema_length,
            slow_ema_length=slow_ema_length,
            atr_length=atr_length,
            atr_multiplier=atr_multiplier,
            sl_atr_multiple=sl_atr_multiple,
            target_rr=target_rr,
            adx_length=adx_length,
            adx_smoothing=adx_smoothing,
            adx_threshold=adx_threshold,
            use_high_volume_buy=use_high_volume_buy,
            volume_length=volume_length,
            volume_multiplier=volume_multiplier,
        )
        self.long_ema_length = max(2, int(long_ema_length))
        self.long_slope_bars = max(1, int(long_slope_bars))
        self.min_atr_percentile = max(0.0, float(min_atr_percentile))
        self.max_atr_percentile = min(100.0, float(max_atr_percentile))
        self.session_start_utc = max(0, min(23, int(session_start_utc)))
        self.session_end_utc = max(1, min(24, int(session_end_utc)))
        self.server_utc_offset_hours = float(server_utc_offset_hours)

    def _series(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        series = super()._series(df)
        close = pd.Series(series["close"])
        atr = pd.Series(series["atr"])
        series["long_ema"] = close.ewm(
            span=self.long_ema_length, adjust=False,
        ).mean().to_numpy()
        series["atr_percentile"] = (
            atr.rolling(252, min_periods=100).rank(pct=True).to_numpy() * 100.0
        )
        return series

    def _utc_stamp(self, value) -> pd.Timestamp:
        stamp = pd.Timestamp(value)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize(
                timezone(timedelta(hours=self.server_utc_offset_hours))
            )
        return stamp.tz_convert("UTC")

    def _in_session(self, value) -> bool:
        stamp = self._utc_stamp(value)
        return (
            stamp.weekday() < 5
            and self.session_start_utc <= stamp.hour < self.session_end_utc
        )

    def _bar_filter(
        self, asset: str, df: pd.DataFrame, series: dict[str, np.ndarray],
        i: int, bullish: bool, bearish: bool, timeframe: str,
    ) -> str | None:
        if asset != "GOLD":
            return "Asset filter: Gold H1 specialization only trades GOLD."
        if timeframe != "H1":
            return "Timeframe filter: Gold specialization requires H1 bars."
        if not self._in_session(df.index[i]):
            return "Session filter: outside configured London/New York liquidity hours."

        atr_pct = series["atr_percentile"][i]
        if not np.isfinite(atr_pct):
            return "Regime filter: ATR percentile is still warming up."
        if not self.min_atr_percentile <= atr_pct <= self.max_atr_percentile:
            return (
                f"Regime filter: ATR percentile {atr_pct:.1f} outside "
                f"{self.min_atr_percentile:.1f}-{self.max_atr_percentile:.1f}."
            )

        prior = i - self.long_slope_bars
        if prior < 0:
            return "Regime filter: long-EMA slope is still warming up."
        long_now = series["long_ema"][i]
        long_prior = series["long_ema"][prior]
        close = series["close"][i]
        if not all(np.isfinite(v) for v in (long_now, long_prior, close)):
            return "Regime filter: long EMA unavailable."
        if bullish and not (close > long_now and long_now > long_prior):
            return "Regime filter: bullish signal lacks rising long-EMA alignment."
        if bearish and not (close < long_now and long_now < long_prior):
            return "Regime filter: bearish signal lacks falling long-EMA alignment."
        return None
