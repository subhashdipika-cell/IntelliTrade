"""Gold hybrid scalp: completed M5 range context with an M1 trigger."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies import indicators as ind
from app.strategies.base import Strategy


class HybridGoldM1Scalp(Strategy):
    name = "Hybrid Gold M1 Scalp"
    scan_timeframe = "M1"

    def __init__(self, context_lookback: int = 24, m5_atr_period: int = 14,
                 m1_atr_period: int = 14, proximity_atr: float = 0.15,
                 stop_buffer_atr: float = 0.20, rr: float = 1.10,
                 min_range_atr: float = 2.5, max_range_atr: float = 10.0,
                 wick_to_body: float = 1.0, max_risk_atr: float = 2.0) -> None:
        self.context_lookback = context_lookback
        self.m5_atr_period = m5_atr_period
        self.m1_atr_period = m1_atr_period
        self.proximity_atr = proximity_atr
        self.stop_buffer_atr = stop_buffer_atr
        self.rr = rr
        self.min_range_atr = min_range_atr
        self.max_range_atr = max_range_atr
        self.wick_to_body = wick_to_body
        self.max_risk_atr = max_risk_atr

    def _context(self, df: pd.DataFrame) -> pd.DataFrame:
        ctx = df[["open", "high", "low", "close"]].resample(
            "5min", label="right", closed="right"
        ).agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        ctx["atr"] = ind.atr(ctx, self.m5_atr_period)
        ctx["ema"] = ind.ema(ctx["close"], 20)
        ctx["support"] = ctx["low"].rolling(self.context_lookback).min().shift(1)
        ctx["resistance"] = ctx["high"].rolling(self.context_lookback).max().shift(1)
        return ctx

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        n = 0 if df is None else len(df)
        out: list[Signal | None] = [None] * n
        if n < 100 or not isinstance(df.index, pd.DatetimeIndex):
            return out
        work = df.sort_index()
        ctx = self._context(work)
        if ctx.empty:
            return out
        m1_atr = ind.atr(work, self.m1_atr_period).to_numpy(dtype=float)
        o = work["open"].to_numpy(dtype=float)
        h = work["high"].to_numpy(dtype=float)
        l = work["low"].to_numpy(dtype=float)
        c = work["close"].to_numpy(dtype=float)
        ctx_times = ctx.index.to_numpy()

        for i, ts in enumerate(work.index):
            a1 = m1_atr[i]
            if not np.isfinite(a1) or a1 <= 0:
                continue
            pos = int(np.searchsorted(ctx_times, ts.to_datetime64(), side="left") - 1)
            if pos < self.context_lookback + self.m5_atr_period:
                continue
            row = ctx.iloc[pos]
            a5, support, resistance, ema = (float(row[k]) for k in ("atr", "support", "resistance", "ema"))
            if not all(np.isfinite(x) for x in (a5, support, resistance, ema)):
                continue
            width = resistance - support
            if width < self.min_range_atr * a5 or width > self.max_range_atr * a5:
                continue
            if abs(float(row["close"]) - ema) > 1.5 * a5:
                continue
            body = abs(c[i] - o[i])
            body_floor = max(body, a1 * 0.05)
            stop_atr = max(a1, 0.20 * a5)
            lower_wick = min(o[i], c[i]) - l[i]
            upper_wick = h[i] - max(o[i], c[i])
            if l[i] <= support + self.proximity_atr * a5 and c[i] > o[i] and lower_wick >= self.wick_to_body * body_floor:
                sl = support - self.stop_buffer_atr * stop_atr
                risk = c[i] - sl
                target = min(c[i] + self.rr * risk, resistance - 0.15 * a5)
                if 0 < risk <= self.max_risk_atr * stop_atr and target > c[i]:
                    out[i] = Signal(asset, Direction.BUY, float(c[i]), round(float(sl), 5), round(float(target), 5), timeframe)
            elif h[i] >= resistance - self.proximity_atr * a5 and c[i] < o[i] and upper_wick >= self.wick_to_body * body_floor:
                sl = resistance + self.stop_buffer_atr * stop_atr
                risk = sl - c[i]
                target = max(c[i] - self.rr * risk, support + 0.15 * a5)
                if 0 < risk <= self.max_risk_atr * stop_atr and target < c[i]:
                    out[i] = Signal(asset, Direction.SELL, float(c[i]), round(float(sl), 5), round(float(target), 5), timeframe)
        return out

    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        signals = self.signals(asset, df, timeframe)
        return signals[-1] if signals else None
