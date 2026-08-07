"""80-20 Bar — Connors & Raschke, *Street Smarts* (1995), the "climax" archetype.

Source note: `E:/Obsidian/Trading_Mind/wiki/sources/street-smarts.md`.

A bar that opens near one end of its range and closes near the other settles the
session's argument decisively: sellers ran it down at the open and buyers took it
back by the close (or the mirror). The vault's reading of the pattern trades the
CARRY-OVER — enter in the direction of the closing extreme on the next bar.

Rules (long; short is the mirror):
  1. The bar opens in the bottom ``threshold`` of its own range.
  2. It closes in the top ``threshold`` of that range.
  3. The range is wide enough to mean something: at least ``min_range_atr`` × ATR.
     Without this a flat, tiny bar trivially satisfies both percentage tests.
  4. Enter in the direction of the close; stop beyond the bar's opposite extreme.

NOTE ON THE SOURCE: the original book's 80-20 is usually stated as a FADE — a
bar that opens in the top 20% and closes in the bottom 20% is sold *into the
following reversal*. The vault's ingested note states it as a continuation of the
closing extreme. That ambiguity is now SETTLED by backtest: ``fade=True`` is
catastrophic on D1 gold and crypto (PF 0.17–0.54, −66% to −90% over full
history), while the continuation reading is the profitable one. The vault's
reading is correct for these instruments; ``fade`` is kept only so the result
stays reproducible.

Backtest, D1, net of spread + commission, 1% risk (2026-07-23):
  rr=1.0   GOLD  PF 1.61 in-sample -> 1.17 out-of-sample   (max DD -5.9%)
           BTC   PF 0.99 -> 1.28
           ETH   PF 0.84 -> 0.82   <- fails BOTH halves; do not deploy on ETH
Default rr is 1.0: it beat rr=2.0 out-of-sample on two of three assets.
GOLD is the strongest fit. H4 was tested and is materially worse than D1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies import indicators as ind
from app.strategies.base import Strategy


class EightyTwenty(Strategy):
    name = "80-20 Bar"
    scan_timeframe = "D1"

    def __init__(self, threshold: float = 0.20, min_range_atr: float = 0.8,
                 rr: float = 1.0, stop_buffer_atr: float = 0.10,
                 atr_period: int = 14, fade: bool = False) -> None:
        self.threshold = threshold
        self.min_range_atr = min_range_atr
        self.rr = rr
        self.stop_buffer_atr = stop_buffer_atr
        self.atr_period = atr_period
        self.fade = fade

    @property
    def _warmup(self) -> int:
        return self.atr_period + 2

    def _series(self, df: pd.DataFrame) -> dict:
        return {
            "open": df["open"].to_numpy(dtype=float),
            "high": df["high"].to_numpy(dtype=float),
            "low": df["low"].to_numpy(dtype=float),
            "close": df["close"].to_numpy(dtype=float),
            "atr": ind.atr(df, self.atr_period).to_numpy(),
        }

    def _decide_at(self, asset: str, s: dict, i: int, timeframe: str) -> Signal | None:
        a = s["atr"][i]
        if np.isnan(a) or a <= 0:
            return None
        o, h, l, c = (float(s[k][i]) for k in ("open", "high", "low", "close"))
        rng = h - l
        if rng <= 0 or rng < self.min_range_atr * a:
            return None

        open_pos = (o - l) / rng    # 0 = at the low, 1 = at the high
        close_pos = (c - l) / rng
        buf = self.stop_buffer_atr * a

        bullish = open_pos <= self.threshold and close_pos >= 1 - self.threshold
        bearish = open_pos >= 1 - self.threshold and close_pos <= self.threshold
        if self.fade:
            bullish, bearish = bearish, bullish

        if bullish:
            sl = round(l - buf, 5)
            risk = c - sl
            if risk > 0:
                return Signal(asset, Direction.BUY, c, sl, round(c + self.rr * risk, 5), timeframe)
        if bearish:
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
