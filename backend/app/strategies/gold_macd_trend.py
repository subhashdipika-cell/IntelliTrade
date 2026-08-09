"""MACD-cross trend strategy adapted from SMT's Gold MACD Trend RR3 rule.

The signal is deliberately deterministic: trade a confirmed MACD cross only
when price is on the matching side of the 200 EMA.  ATR normalizes the stop and
the target is fixed at 3R, matching SMT's tested rule.  The strategy is generic
enough for backtesting, but its scanner deployment should remain asset-scoped.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies import indicators as ind
from app.strategies.base import Strategy


class GoldMacdTrend(Strategy):
    name = "SMT Gold MACD Trend RR3"
    scan_timeframe = "H1"

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9,
                 trend_period: int = 200, atr_period: int = 14,
                 sl_atr: float = 1.5, rr: float = 3.0) -> None:
        self.fast = fast
        self.slow = slow
        self.signal_period = signal
        self.trend_period = trend_period
        self.atr_period = atr_period
        self.sl_atr = sl_atr
        self.rr = rr

    def _series(self, df: pd.DataFrame) -> dict:
        line, sig = ind.macd(df["close"], self.fast, self.slow, self.signal_period)
        return {
            "close": df["close"].to_numpy(dtype=float),
            "ema": ind.ema(df["close"], self.trend_period).to_numpy(dtype=float),
            "line": line.to_numpy(dtype=float),
            "sig": sig.to_numpy(dtype=float),
            "atr": ind.atr(df, self.atr_period).to_numpy(dtype=float),
        }

    def _decide_at(self, asset: str, s: dict, i: int, timeframe: str) -> Signal | None:
        a = s["atr"][i]
        if not np.isfinite(a) or a <= 0 or not np.isfinite(s["ema"][i]):
            return None
        prev_diff = s["line"][i - 1] - s["sig"][i - 1]
        curr_diff = s["line"][i] - s["sig"][i]
        if not np.isfinite(prev_diff) or not np.isfinite(curr_diff):
            return None
        price = float(s["close"][i])
        if prev_diff <= 0 < curr_diff and price > s["ema"][i]:
            sl, tp = ind.bracket("BUY", price, a, self.sl_atr, self.rr)
            return Signal(asset, Direction.BUY, price, sl, tp, timeframe)
        if prev_diff >= 0 > curr_diff and price < s["ema"][i]:
            sl, tp = ind.bracket("SELL", price, a, self.sl_atr, self.rr)
            return Signal(asset, Direction.SELL, price, sl, tp, timeframe)
        return None

    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        if df is None or len(df) < self.trend_period + 2:
            return None
        return self._decide_at(asset, self._series(df), len(df) - 1, timeframe)

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        n = 0 if df is None else len(df)
        out: list[Signal | None] = [None] * n
        if n < self.trend_period + 2:
            return out
        s = self._series(df)
        for i in range(self.trend_period + 1, n):
            out[i] = self._decide_at(asset, s, i, timeframe)
        return out
