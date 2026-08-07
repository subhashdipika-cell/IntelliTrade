"""Momentum Pinball — Connors & Raschke, *Street Smarts* (1995).

Source note: `E:/Obsidian/Trading_Mind/wiki/sources/street-smarts.md`.
The direct ancestor of Connors's later ConnorsRSI work.

A very short-lookback RSI is a stretch gauge, not a trend gauge: RSI(2) below 30
means the market has been pushed down hard and fast. The pattern waits for the
snap-back to actually begin — the next bar must close above its own open — before
committing. That confirmation bar is what separates this from catching a falling
knife, and it matches the book's core instruction to enter only after the market
has already turned.

Rules (long; short is the mirror):
  1. The PREVIOUS bar's RSI(``rsi_period``) closed below ``oversold``.
  2. THIS bar closes above its own open — buyers showed up.
  3. Stop below this bar's low; target at ``rr`` × risk.

Both the RSI read and the confirmation come from closed bars, so the signal is
causal and the vectorised path matches bar-by-bar evaluation exactly.

Backtest, D1, net of spread + commission, 1% risk, rr=2.0 (2026-07-23):
  BTC   PF 1.05 in-sample -> 1.27 out-of-sample   (n=149 / 71)
  ETH   PF 1.07 -> 1.09                           (n=210 / 91)
  GOLD  PF 0.91 -> 2.83                           (OOS n=22 only — too few to trust)
This is the most CONSISTENT of the three Street Smarts patterns tested: both
crypto legs are positive in both halves. The edge is modest (PF ~1.1), not
spectacular. rr=2.0 clearly beat 1.0 and 1.5. H4 was tested and loses.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies import indicators as ind
from app.strategies.base import Strategy


class MomentumPinball(Strategy):
    name = "Momentum Pinball"
    scan_timeframe = "D1"

    def __init__(self, rsi_period: int = 2, oversold: float = 30.0,
                 overbought: float = 70.0, rr: float = 2.0,
                 stop_buffer_atr: float = 0.10, atr_period: int = 14) -> None:
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.rr = rr
        self.stop_buffer_atr = stop_buffer_atr
        self.atr_period = atr_period

    @property
    def _warmup(self) -> int:
        return self.atr_period + self.rsi_period + 2

    def _series(self, df: pd.DataFrame) -> dict:
        return {
            "open": df["open"].to_numpy(dtype=float),
            "high": df["high"].to_numpy(dtype=float),
            "low": df["low"].to_numpy(dtype=float),
            "close": df["close"].to_numpy(dtype=float),
            # Previous bar's RSI — the setup condition, read one bar back.
            "rsi_prev": ind.rsi(df["close"], self.rsi_period).shift(1).to_numpy(),
            "atr": ind.atr(df, self.atr_period).to_numpy(),
        }

    def _decide_at(self, asset: str, s: dict, i: int, timeframe: str) -> Signal | None:
        a, r_prev = s["atr"][i], s["rsi_prev"][i]
        if np.isnan(a) or np.isnan(r_prev) or a <= 0:
            return None
        o, h, l, c = (float(s[k][i]) for k in ("open", "high", "low", "close"))
        buf = self.stop_buffer_atr * a

        if r_prev < self.oversold and c > o:
            sl = round(l - buf, 5)
            risk = c - sl
            if risk > 0:
                return Signal(asset, Direction.BUY, c, sl, round(c + self.rr * risk, 5), timeframe)
        if r_prev > self.overbought and c < o:
            sl = round(h + buf, 5)
            risk = sl - c
            if risk > 0:
                return Signal(asset, Direction.SELL, c, sl, round(c - self.rr * risk, 5), timeframe)
        return None

    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        if df is None or len(df) < self._warmup:
            return None
        return self._decide_at(asset, self._series(df), len(df) - 1, timeframe)

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        n = 0 if df is None else len(df)
        out: list[Signal | None] = [None] * n
        if n < self._warmup:
            return out
        s = self._series(df)
        for i in range(self._warmup, n):
            out[i] = self._decide_at(asset, s, i, timeframe)
        return out
