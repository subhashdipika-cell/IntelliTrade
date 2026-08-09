"""Range-bound support/resistance reversion scalp.

The strategy trades only when the recent range is sufficiently broad relative
to ATR and the EMA slope is quiet.  It then waits for a rejection candle near
the prior rolling support/resistance.  Stops sit just beyond the rejected
level and targets are deliberately modest, capped before the opposite edge of
the range.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies import indicators as ind
from app.strategies.base import Strategy


class RangeReversionScalp(Strategy):
    name = "Range Reversion Scalp"
    scan_timeframe = "M5"

    def __init__(self, lookback: int = 48, atr_period: int = 14,
                 ema_period: int = 20, slope_bars: int = 8,
                 min_range_atr: float = 3.0, max_range_atr: float = 12.0,
                 proximity_atr: float = 0.15, stop_buffer_atr: float = 0.10,
                 rr: float = 1.10, target_buffer_atr: float = 0.20,
                 wick_to_body: float = 1.0, max_risk_atr: float = 1.25) -> None:
        self.lookback = lookback
        self.atr_period = atr_period
        self.ema_period = ema_period
        self.slope_bars = slope_bars
        self.min_range_atr = min_range_atr
        self.max_range_atr = max_range_atr
        self.proximity_atr = proximity_atr
        self.stop_buffer_atr = stop_buffer_atr
        self.rr = rr
        self.target_buffer_atr = target_buffer_atr
        self.wick_to_body = wick_to_body
        self.max_risk_atr = max_risk_atr

    def _scan(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        n = 0 if df is None else len(df)
        out: list[Signal | None] = [None] * n
        warmup = max(self.lookback + 1, self.ema_period + self.slope_bars,
                     self.atr_period + 2)
        if n < warmup:
            return out

        o = df["open"].to_numpy(dtype=float)
        h = df["high"].to_numpy(dtype=float)
        l = df["low"].to_numpy(dtype=float)
        c = df["close"].to_numpy(dtype=float)
        atr = ind.atr(df, self.atr_period).to_numpy(dtype=float)
        ema = ind.ema(df["close"], self.ema_period).to_numpy(dtype=float)
        support = df["low"].rolling(self.lookback).min().shift(1).to_numpy()
        resistance = df["high"].rolling(self.lookback).max().shift(1).to_numpy()

        for i in range(warmup, n):
            a = atr[i]
            if not np.isfinite(a) or a <= 0 or not np.isfinite(support[i]) or not np.isfinite(resistance[i]):
                continue
            width = resistance[i] - support[i]
            if width < self.min_range_atr * a or width > self.max_range_atr * a:
                continue
            if abs(ema[i] - ema[i - self.slope_bars]) > 0.75 * a:
                continue

            body = abs(c[i] - o[i])
            body_floor = max(body, a * 0.05)
            lower_wick = min(o[i], c[i]) - l[i]
            upper_wick = h[i] - max(o[i], c[i])
            lower_touch = l[i] <= support[i] + self.proximity_atr * a
            upper_touch = h[i] >= resistance[i] - self.proximity_atr * a

            if lower_touch and c[i] > o[i] and lower_wick >= self.wick_to_body * body_floor:
                sl = support[i] - self.stop_buffer_atr * a
                risk = c[i] - sl
                target = min(c[i] + self.rr * risk,
                             resistance[i] - self.target_buffer_atr * a)
                if 0 < risk <= self.max_risk_atr * a and target > c[i]:
                    out[i] = Signal(asset, Direction.BUY, float(c[i]),
                                    round(float(sl), 5), round(float(target), 5), timeframe)
            elif upper_touch and c[i] < o[i] and upper_wick >= self.wick_to_body * body_floor:
                sl = resistance[i] + self.stop_buffer_atr * a
                risk = sl - c[i]
                target = max(c[i] - self.rr * risk,
                             support[i] + self.target_buffer_atr * a)
                if 0 < risk <= self.max_risk_atr * a and target < c[i]:
                    out[i] = Signal(asset, Direction.SELL, float(c[i]),
                                    round(float(sl), 5), round(float(target), 5), timeframe)
        return out

    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        signals = self._scan(asset, df, timeframe)
        return signals[-1] if signals else None

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        return self._scan(asset, df, timeframe)
