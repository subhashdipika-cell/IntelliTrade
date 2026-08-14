"""Gold London/New-York volatility trend continuation.

The strategy is deliberately mechanical and causal:
  * a 1H trend/ADX/volatility regime is projected from closed M15 bars;
  * a M15 Donchian break must retest and reject the broken level;
  * entries are limited to the liquid London/New-York overlap.

Timestamps are interpreted as UTC when naive.  A broker adapter should pass
UTC-indexed data; the IANA timezone conversion below keeps the overlap correct
through London/New York daylight-saving changes.
"""
from __future__ import annotations

from datetime import timedelta, timezone

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies import indicators as ind
from app.strategies.base import Strategy


class GoldSessionBreakRetest(Strategy):
    name = "Gold Session Break Retest"
    scan_timeframe = "M15"
    scan_lookback = 1600

    def __init__(
        self,
        lookback: int = 20,
        retest_window: int = 4,
        atr_period: int = 14,
        regime_fast: int = 20,
        regime_slow: int = 50,
        regime_long: int = 200,
        adx_period: int = 14,
        min_adx: float = 20.0,
        min_atr_percentile: float = 25.0,
        max_atr_percentile: float = 90.0,
        break_atr: float = 0.10,
        retest_atr: float = 0.15,
        stop_buffer_atr: float = 0.25,
        min_risk_atr: float = 0.75,
        max_risk_atr: float = 2.0,
        rr: float = 1.8,
        server_utc_offset_hours: float = 3.0,
    ) -> None:
        self.lookback = lookback
        self.retest_window = retest_window
        self.atr_period = atr_period
        self.regime_fast = regime_fast
        self.regime_slow = regime_slow
        self.regime_long = regime_long
        self.adx_period = adx_period
        self.min_adx = min_adx
        self.min_atr_percentile = min_atr_percentile
        self.max_atr_percentile = max_atr_percentile
        self.break_atr = break_atr
        self.retest_atr = retest_atr
        self.stop_buffer_atr = stop_buffer_atr
        self.min_risk_atr = min_risk_atr
        self.max_risk_atr = max_risk_atr
        self.rr = rr
        self.server_utc_offset_hours = server_utc_offset_hours

    @staticmethod
    def _adx(df: pd.DataFrame, period: int) -> pd.Series:
        high, low, close = df["high"], df["low"], df["close"]
        up = high.diff()
        down = -low.diff()
        plus_dm = up.where((up > down) & (up > 0), 0.0)
        minus_dm = down.where((down > up) & (down > 0), 0.0)
        tr = pd.concat(
            [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(period).mean().replace(0, np.nan)
        plus_di = 100 * plus_dm.rolling(period).mean() / atr
        minus_di = 100 * minus_dm.rolling(period).mean() / atr
        dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).replace(
            [np.inf, -np.inf], np.nan
        )
        return dx.rolling(period).mean()

    def _in_overlap(self, ts) -> bool:
        stamp = pd.Timestamp(ts)
        if stamp.tzinfo is None:
            # Vantage MT5 bars are broker-server timestamps.  The current
            # Vantage profile is UTC+3; callers with already-normalized UTC
            # data can pass server_utc_offset_hours=0.
            stamp = stamp.tz_localize(
                timezone(timedelta(hours=self.server_utc_offset_hours))
            ).tz_convert("UTC")
        else:
            stamp = stamp.tz_convert("UTC")
        london = stamp.tz_convert("Europe/London")
        new_york = stamp.tz_convert("America/New_York")
        london_min = london.hour * 60 + london.minute
        ny_min = new_york.hour * 60 + new_york.minute
        # London afternoon and New York morning; DST conversion is automatic.
        return 13 * 60 + 30 <= london_min < 17 * 60 and 8 * 60 + 30 <= ny_min < 12 * 60

    def _scan(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        n = 0 if df is None else len(df)
        out: list[Signal | None] = [None] * n
        if asset != "GOLD" or n < self.regime_long * 4 + self.lookback + 10:
            return out

        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        atr = ind.atr(df, self.atr_period)
        fast = ind.ema(close, self.regime_fast * 4)
        slow = ind.ema(close, self.regime_slow * 4)
        long_ema = ind.ema(close, self.regime_long * 4)
        adx = self._adx(df, self.adx_period * 4)
        atr_pct = atr.rolling(252 * 4, min_periods=100 * 4).rank(pct=True) * 100
        prior_high = high.rolling(self.lookback).max().shift(1)
        prior_low = low.rolling(self.lookback).min().shift(1)

        pending = 0
        level = np.nan
        age = 0
        for i in range(self.regime_long * 4 + self.lookback + 5, n):
            a = float(atr.iloc[i]) if np.isfinite(atr.iloc[i]) else np.nan
            if not np.isfinite(a) or a <= 0 or not self._in_overlap(df.index[i]):
                continue
            trend_up = (
                fast.iloc[i] > slow.iloc[i] > long_ema.iloc[i]
                and fast.iloc[i] > fast.iloc[i - 5]
            )
            trend_down = (
                fast.iloc[i] < slow.iloc[i] < long_ema.iloc[i]
                and fast.iloc[i] < fast.iloc[i - 5]
            )
            regime_ok = (
                np.isfinite(adx.iloc[i])
                and adx.iloc[i] >= self.min_adx
                and np.isfinite(atr_pct.iloc[i])
                and self.min_atr_percentile <= atr_pct.iloc[i] <= self.max_atr_percentile
            )
            if not regime_ok:
                pending = 0
                continue

            c, h, l = float(close.iloc[i]), float(high.iloc[i]), float(low.iloc[i])
            if pending:
                age += 1
                if age > self.retest_window:
                    pending = 0
                elif pending == 1 and trend_up:
                    if c < level - self.retest_atr * a:
                        pending = 0
                    elif l <= level + self.retest_atr * a and c > level:
                        sl = min(l, level) - self.stop_buffer_atr * a
                        risk = c - sl
                        if self.min_risk_atr * a <= risk <= self.max_risk_atr * a:
                            out[i] = Signal(asset, Direction.BUY, c, round(sl, 5),
                                            round(c + self.rr * risk, 5), timeframe)
                            pending = 0
                elif pending == -1 and trend_down:
                    if c > level + self.retest_atr * a:
                        pending = 0
                    elif h >= level - self.retest_atr * a and c < level:
                        sl = max(h, level) + self.stop_buffer_atr * a
                        risk = sl - c
                        if self.min_risk_atr * a <= risk <= self.max_risk_atr * a:
                            out[i] = Signal(asset, Direction.SELL, c, round(sl, 5),
                                            round(c - self.rr * risk, 5), timeframe)
                            pending = 0

            if pending == 0 and trend_up and c > float(prior_high.iloc[i]) + self.break_atr * a:
                pending, level, age = 1, float(prior_high.iloc[i]), 0
            elif pending == 0 and trend_down and c < float(prior_low.iloc[i]) - self.break_atr * a:
                pending, level, age = -1, float(prior_low.iloc[i]), 0
        return out

    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        signals = self._scan(asset, df, timeframe)
        return signals[-1] if signals else None

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        return self._scan(asset, df, timeframe)
