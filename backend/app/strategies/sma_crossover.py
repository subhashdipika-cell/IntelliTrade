"""Reference strategy: SMA crossover with ATR-based SL/TP.

Signal is generated only on the most recent *closed* bar (we read iloc[-2] vs
iloc[-1] crossovers off completed candles) to avoid acting on a forming bar.

Indicator math lives in _series() (computed once) and the per-bar rule in
_decide_at(); generate() (live) and signals() (backtest) both reuse them."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies.base import Strategy


class SmaCrossover(Strategy):
    name = "SMA Crossover"

    def __init__(self, fast: int = 50, slow: int = 200,
                 atr_period: int = 14, sl_atr: float = 1.5, rr: float = 2.0) -> None:
        self.fast, self.slow = fast, slow
        self.atr_period, self.sl_atr, self.rr = atr_period, sl_atr, rr

    def _series(self, df: pd.DataFrame) -> dict:
        close = df["close"]
        return {
            "close": close.to_numpy(dtype=float),
            "fast": close.rolling(self.fast).mean().to_numpy(),
            "slow": close.rolling(self.slow).mean().to_numpy(),
            "atr": self._atr(df, self.atr_period).to_numpy(),
        }

    def _decide_at(self, asset: str, s: dict, i: int, timeframe: str) -> Signal | None:
        a = s["atr"][i]
        if np.isnan(a) or a == 0:
            return None
        prev_diff = s["fast"][i - 1] - s["slow"][i - 1]
        curr_diff = s["fast"][i] - s["slow"][i]
        if np.isnan(prev_diff) or np.isnan(curr_diff):
            return None
        price = float(s["close"][i])
        if prev_diff <= 0 < curr_diff:      # bullish cross
            sl = price - self.sl_atr * a
            tp = price + self.sl_atr * a * self.rr
            return Signal(asset, Direction.BUY, price, round(sl, 5), round(tp, 5), timeframe)
        if prev_diff >= 0 > curr_diff:      # bearish cross
            sl = price + self.sl_atr * a
            tp = price - self.sl_atr * a * self.rr
            return Signal(asset, Direction.SELL, price, round(sl, 5), round(tp, 5), timeframe)
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

    @staticmethod
    def _atr(df: pd.DataFrame, period: int) -> pd.Series:
        hl = df["high"] - df["low"]
        hc = (df["high"] - df["close"].shift()).abs()
        lc = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        return tr.rolling(period).mean()
