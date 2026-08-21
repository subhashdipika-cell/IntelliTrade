"""Bitcoin 4H-regime / 1H breakout-retest strategy.

This is price-only by default so it remains reproducible with MT5 data.  A
funding z-score can be supplied by a future derivative-data adapter, but it is
not silently inferred from an unrelated exchange.
"""
from __future__ import annotations

from datetime import timedelta, timezone

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies import indicators as ind
from app.strategies.base import Strategy


class BtcVolatilityBreakRetest(Strategy):
    name = "BTC Volatility Break Retest"
    scan_timeframe = "H1"
    scan_lookback = 1400

    def __init__(
        self,
        lookback: int = 20,
        retest_window: int = 6,
        atr_period: int = 14,
        regime_fast: int = 50,
        regime_slow: int = 200,
        adx_period: int = 14,
        min_adx: float = 18.0,
        min_atr_percentile: float = 15.0,
        max_atr_percentile: float = 95.0,
        break_atr: float = 0.15,
        retest_atr: float = 0.20,
        stop_buffer_atr: float = 0.20,
        min_risk_atr: float = 0.80,
        max_risk_atr: float = 2.50,
        rr: float = 2.0,
        server_utc_offset_hours: float = 3.0,
    ) -> None:
        self.lookback = lookback
        self.retest_window = retest_window
        self.atr_period = atr_period
        self.regime_fast = regime_fast
        self.regime_slow = regime_slow
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
        up, down = high.diff(), -low.diff()
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

    def _weekday_session(self, ts) -> bool:
        stamp = pd.Timestamp(ts)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize(
                timezone(timedelta(hours=self.server_utc_offset_hours))
            ).tz_convert("UTC")
        else:
            stamp = stamp.tz_convert("UTC")
        # Conservative weekend rule: no new entries from Friday 20:00 UTC
        # through Sunday 20:00 UTC. Existing risk management remains active.
        if stamp.weekday() == 4 and stamp.hour >= 20:
            return False
        if stamp.weekday() == 5:
            return False
        if stamp.weekday() == 6 and stamp.hour < 20:
            return False
        return True

    def _scan(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        n = 0 if df is None else len(df)
        out: list[Signal | None] = [None] * n
        if asset != "BTC":
            self.last_reason = "Asset filter: strategy is scoped to BTC."
            return out
        minimum = self.regime_slow + self.lookback + 10
        if n < minimum:
            self.last_reason = f"Insufficient history: {n} bars; need {minimum}."
            return out

        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        atr = ind.atr(df, self.atr_period)
        fast = ind.ema(close, self.regime_fast)
        slow = ind.ema(close, self.regime_slow)
        adx = self._adx(df, self.adx_period)
        atr_pct = atr.rolling(252, min_periods=100).rank(pct=True) * 100
        prior_high = high.rolling(self.lookback).max().shift(1)
        prior_low = low.rolling(self.lookback).min().shift(1)

        pending = 0
        level = np.nan
        age = 0
        last_reason = "No breakout or retest confirmed on the latest closed bar."
        for i in range(self.regime_slow + self.lookback + 5, n):
            a = float(atr.iloc[i]) if np.isfinite(atr.iloc[i]) else np.nan
            if not np.isfinite(a) or a <= 0:
                last_reason = "Volatility filter: ATR unavailable or zero."
                pending = 0
                continue
            if not self._weekday_session(df.index[i]):
                last_reason = "Weekend filter: new BTC entries are paused."
                pending = 0
                continue
            up = fast.iloc[i] > slow.iloc[i] and fast.iloc[i] > fast.iloc[i - 3]
            down = fast.iloc[i] < slow.iloc[i] and fast.iloc[i] < fast.iloc[i - 3]
            regime_ok = (
                np.isfinite(adx.iloc[i])
                and adx.iloc[i] >= self.min_adx
                and np.isfinite(atr_pct.iloc[i])
                and self.min_atr_percentile <= atr_pct.iloc[i] <= self.max_atr_percentile
            )
            if not regime_ok:
                last_reason = "Regime filter: ADX or ATR percentile outside bounds."
                pending = 0
                continue

            c, h, l = float(close.iloc[i]), float(high.iloc[i]), float(low.iloc[i])
            bar_range = h - l
            if bar_range > 2.5 * a:
                last_reason = "Volatility shock filter: candle range exceeds 2.5 ATR."
                pending = 0
                continue
            if pending:
                age += 1
                if age > self.retest_window:
                    pending = 0
                elif pending == 1 and up:
                    if c < level - self.retest_atr * a:
                        pending = 0
                    elif l <= level + self.retest_atr * a and c > level:
                        sl = min(l, level) - self.stop_buffer_atr * a
                        risk = c - sl
                        if self.min_risk_atr * a <= risk <= self.max_risk_atr * a:
                            out[i] = Signal(asset, Direction.BUY, c, round(sl, 5),
                                            round(c + self.rr * risk, 5), timeframe)
                            last_reason = "Signal confirmed: bullish breakout retest."
                            pending = 0
                elif pending == -1 and down:
                    if c > level + self.retest_atr * a:
                        pending = 0
                    elif h >= level - self.retest_atr * a and c < level:
                        sl = max(h, level) + self.stop_buffer_atr * a
                        risk = sl - c
                        if self.min_risk_atr * a <= risk <= self.max_risk_atr * a:
                            out[i] = Signal(asset, Direction.SELL, c, round(sl, 5),
                                            round(c - self.rr * risk, 5), timeframe)
                            last_reason = "Signal confirmed: bearish breakout retest."
                            pending = 0

            if pending == 0 and up and c > float(prior_high.iloc[i]) + self.break_atr * a:
                pending, level, age = 1, float(prior_high.iloc[i]), 0
                last_reason = "Breakout detected: waiting for bullish retest."
            elif pending == 0 and down and c < float(prior_low.iloc[i]) - self.break_atr * a:
                pending, level, age = -1, float(prior_low.iloc[i]), 0
                last_reason = "Breakout detected: waiting for bearish retest."
        self.last_reason = last_reason
        return out

    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        signals = self._scan(asset, df, timeframe)
        return signals[-1] if signals else None

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        return self._scan(asset, df, timeframe)
