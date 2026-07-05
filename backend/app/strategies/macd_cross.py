"""MACD signal-line crossover: momentum strategy."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies import indicators as ind
from app.strategies.base import Strategy

_MIN_BARS = 40


class MacdCross(Strategy):
    name = "MACD Cross"

    def __init__(self, atr_period: int = 14, sl_atr: float = 1.5, rr: float = 2.0) -> None:
        self.atr_period, self.sl_atr, self.rr = atr_period, sl_atr, rr

    def _series(self, df: pd.DataFrame) -> dict:
        line, sig = ind.macd(df["close"])
        return {
            "close": df["close"].to_numpy(dtype=float),
            "line": line.to_numpy(),
            "sig": sig.to_numpy(),
            "atr": ind.atr(df, self.atr_period).to_numpy(),
        }

    def _decide_at(self, asset: str, s: dict, i: int, timeframe: str) -> Signal | None:
        a = s["atr"][i]
        if np.isnan(a) or a == 0:
            return None
        prev_diff = s["line"][i - 1] - s["sig"][i - 1]
        curr_diff = s["line"][i] - s["sig"][i]
        if np.isnan(prev_diff) or np.isnan(curr_diff):
            return None
        price = float(s["close"][i])
        if prev_diff <= 0 < curr_diff:
            sl, tp = ind.bracket("BUY", price, a, self.sl_atr, self.rr)
            return Signal(asset, Direction.BUY, price, sl, tp, timeframe)
        if prev_diff >= 0 > curr_diff:
            sl, tp = ind.bracket("SELL", price, a, self.sl_atr, self.rr)
            return Signal(asset, Direction.SELL, price, sl, tp, timeframe)
        return None

    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        if df is None or len(df) < _MIN_BARS:
            return None
        return self._decide_at(asset, self._series(df), len(df) - 1, timeframe)

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        n = 0 if df is None else len(df)
        out: list[Signal | None] = [None] * n
        if n < _MIN_BARS:
            return out
        s = self._series(df)
        for i in range(_MIN_BARS - 1, n):
            out[i] = self._decide_at(asset, s, i, timeframe)
        return out
