"""RSI mean-reversion: buy oversold, sell overbought. Works in ranges, struggles
in strong trends — useful contrast to the trend strategies."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies import indicators as ind
from app.strategies.base import Strategy


class RsiReversion(Strategy):
    name = "RSI Reversion"

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70,
                 atr_period: int = 14, sl_atr: float = 1.5, rr: float = 1.5) -> None:
        self.period, self.oversold, self.overbought = period, oversold, overbought
        self.atr_period, self.sl_atr, self.rr = atr_period, sl_atr, rr

    def _series(self, df: pd.DataFrame) -> dict:
        return {
            "close": df["close"].to_numpy(dtype=float),
            "rsi": ind.rsi(df["close"], self.period).to_numpy(),
            "atr": ind.atr(df, self.atr_period).to_numpy(),
        }

    def _decide_at(self, asset: str, s: dict, i: int, timeframe: str) -> Signal | None:
        r = s["rsi"][i]
        a = s["atr"][i]
        if np.isnan(r) or np.isnan(a) or a == 0:
            return None
        price = float(s["close"][i])
        if r < self.oversold:
            sl, tp = ind.bracket("BUY", price, a, self.sl_atr, self.rr)
            return Signal(asset, Direction.BUY, price, sl, tp, timeframe)
        if r > self.overbought:
            sl, tp = ind.bracket("SELL", price, a, self.sl_atr, self.rr)
            return Signal(asset, Direction.SELL, price, sl, tp, timeframe)
        return None

    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        if df is None or len(df) < self.period + 2:
            return None
        return self._decide_at(asset, self._series(df), len(df) - 1, timeframe)

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        n = 0 if df is None else len(df)
        out: list[Signal | None] = [None] * n
        if n < self.period + 2:
            return out
        s = self._series(df)
        for i in range(self.period + 1, n):
            out[i] = self._decide_at(asset, s, i, timeframe)
        return out
