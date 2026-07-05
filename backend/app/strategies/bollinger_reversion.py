"""Bollinger Band reversion: buy a close below the lower band, sell a close above
the upper band. Volatility mean-reversion."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies import indicators as ind
from app.strategies.base import Strategy


class BollingerReversion(Strategy):
    name = "Bollinger Reversion"

    def __init__(self, period: int = 20, k: float = 2.0,
                 atr_period: int = 14, sl_atr: float = 1.5, rr: float = 1.5) -> None:
        self.period, self.k = period, k
        self.atr_period, self.sl_atr, self.rr = atr_period, sl_atr, rr

    def _series(self, df: pd.DataFrame) -> dict:
        _, upper, lower = ind.bollinger(df["close"], self.period, self.k)
        return {
            "close": df["close"].to_numpy(dtype=float),
            "upper": upper.to_numpy(),
            "lower": lower.to_numpy(),
            "atr": ind.atr(df, self.atr_period).to_numpy(),
        }

    def _decide_at(self, asset: str, s: dict, i: int, timeframe: str) -> Signal | None:
        a = s["atr"][i]
        if np.isnan(a) or a == 0:
            return None
        upper, lower = s["upper"][i], s["lower"][i]
        if np.isnan(upper) or np.isnan(lower):
            return None
        price = float(s["close"][i])
        if price < lower:
            sl, tp = ind.bracket("BUY", price, a, self.sl_atr, self.rr)
            return Signal(asset, Direction.BUY, price, sl, tp, timeframe)
        if price > upper:
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
