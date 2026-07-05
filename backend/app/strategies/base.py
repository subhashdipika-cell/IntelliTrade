"""Strategy interface. Concrete strategies subclass this and implement generate().

Two entry points, ONE source of truth:
  • generate() — decide on the latest closed bar (live pipeline / scanner).
  • signals()  — one optional Signal per bar in a single vectorized pass, for
                 backtesting. The default below is a correct-but-slow fallback
                 (calls generate() on growing windows, O(n^2)); strategies should
                 override it to compute indicators once and iterate, making a
                 backtest O(n). Because pandas rolling/ewm are causal, the
                 vectorised value at bar i equals generate() on df[:i+1], so the
                 fast path returns identical results."""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from app.pipeline.context import Signal


class Strategy(ABC):
    name: str = "strategy"

    @abstractmethod
    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        """Return a Signal if the latest bar fires a setup, else None."""
        raise NotImplementedError

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        """One optional Signal per bar (index-aligned). Slow default; override."""
        n = 0 if df is None else len(df)
        out: list[Signal | None] = [None] * n
        for i in range(2, n):
            out[i] = self.generate(asset, df.iloc[: i + 1], timeframe)
        return out
