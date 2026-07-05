"""Donchian channel breakout: go long when price breaks the prior N-bar high,
short on the prior N-bar low. ATR-based SL/TP. Fires far more often than the
50/200 SMA cross, so it's useful for exercising live signals."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies.base import Strategy


class DonchianBreakout(Strategy):
    name = "Donchian Breakout"

    def __init__(self, channel: int = 20, atr_period: int = 14,
                 sl_atr: float = 1.5, rr: float = 2.0) -> None:
        self.channel = channel
        self.atr_period = atr_period
        self.sl_atr = sl_atr
        self.rr = rr

    def _series(self, df: pd.DataFrame) -> dict:
        return {
            "close": df["close"].to_numpy(dtype=float),
            "upper": df["high"].rolling(self.channel).max().to_numpy(),
            "lower": df["low"].rolling(self.channel).min().to_numpy(),
            "atr": self._atr(df, self.atr_period).to_numpy(),
        }

    def _decide_at(self, asset: str, s: dict, i: int, timeframe: str) -> Signal | None:
        atr = s["atr"][i]
        if np.isnan(atr) or atr == 0:
            return None
        # prior-bar channel (exclude the forming bar to avoid lookahead)
        upper, lower = s["upper"][i - 1], s["lower"][i - 1]
        if np.isnan(upper) or np.isnan(lower):
            return None
        price = float(s["close"][i])
        if price > upper:
            sl = price - self.sl_atr * atr
            tp = price + self.sl_atr * atr * self.rr
            return Signal(asset, Direction.BUY, price, round(sl, 5), round(tp, 5), timeframe)
        if price < lower:
            sl = price + self.sl_atr * atr
            tp = price - self.sl_atr * atr * self.rr
            return Signal(asset, Direction.SELL, price, round(sl, 5), round(tp, 5), timeframe)
        return None

    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        if df is None or len(df) < self.channel + 2:
            return None
        return self._decide_at(asset, self._series(df), len(df) - 1, timeframe)

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        n = 0 if df is None else len(df)
        out: list[Signal | None] = [None] * n
        if n < self.channel + 2:
            return out
        s = self._series(df)
        for i in range(self.channel + 1, n):
            out[i] = self._decide_at(asset, s, i, timeframe)
        return out

    @staticmethod
    def _atr(df: pd.DataFrame, period: int) -> pd.Series:
        hl = df["high"] - df["low"]
        hc = (df["high"] - df["close"].shift()).abs()
        lc = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        return tr.rolling(period).mean()
