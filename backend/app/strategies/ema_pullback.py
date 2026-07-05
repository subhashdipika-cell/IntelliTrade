"""EMA trend-pullback: trade in the direction of the 50/200 trend when price
reclaims the fast EMA after a pullback. Trend-following with better entries than
a raw crossover."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies import indicators as ind
from app.strategies.base import Strategy


class EmaPullback(Strategy):
    name = "EMA Pullback"

    def __init__(self, fast: int = 20, mid: int = 50, slow: int = 200,
                 atr_period: int = 14, sl_atr: float = 1.5, rr: float = 2.0) -> None:
        self.fast, self.mid, self.slow = fast, mid, slow
        self.atr_period, self.sl_atr, self.rr = atr_period, sl_atr, rr

    def _series(self, df: pd.DataFrame) -> dict:
        close = df["close"]
        return {
            "close": close.to_numpy(dtype=float),
            "e_fast": ind.ema(close, self.fast).to_numpy(),
            "e_mid": ind.ema(close, self.mid).to_numpy(),
            "e_slow": ind.ema(close, self.slow).to_numpy(),
            "atr": ind.atr(df, self.atr_period).to_numpy(),
        }

    def _decide_at(self, asset: str, s: dict, i: int, timeframe: str) -> Signal | None:
        a = s["atr"][i]
        if np.isnan(a) or a == 0:
            return None
        price = float(s["close"][i])
        prev = float(s["close"][i - 1])
        uptrend = s["e_mid"][i] > s["e_slow"][i]
        downtrend = s["e_mid"][i] < s["e_slow"][i]
        reclaim_up = prev < s["e_fast"][i - 1] and price > s["e_fast"][i]
        reclaim_dn = prev > s["e_fast"][i - 1] and price < s["e_fast"][i]

        if uptrend and reclaim_up:
            sl, tp = ind.bracket("BUY", price, a, self.sl_atr, self.rr)
            return Signal(asset, Direction.BUY, price, sl, tp, timeframe)
        if downtrend and reclaim_dn:
            sl, tp = ind.bracket("SELL", price, a, self.sl_atr, self.rr)
            return Signal(asset, Direction.SELL, price, sl, tp, timeframe)
        return None

    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        if df is None or len(df) < self.slow + 2:
            return None
        return self._decide_at(asset, self._series(df), len(df) - 1, timeframe)

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        n = 0 if df is None else len(df)
        out: list[Signal | None] = [None] * n
        if n < self.slow + 2:
            return out
        s = self._series(df)
        for i in range(self.slow + 1, n):
            out[i] = self._decide_at(asset, s, i, timeframe)
        return out
