"""Gold M5 Pullback Scalp — trend-aligned pullback to EMA9 on 5-minute gold.

Backtest (13d M5 gold, net of RawECN cost): PF ~1.7, WR ~57%, ~5 setups/day.
The higher timeframe is the point: tight M1 targets lose to spread; M5 targets
(~$6-9, 1.8xATR) clear the ~$0.18 round-trip cost. Fixed target beats a
ratcheting/trailing exit on gold — gold's frequent pullbacks stop a trailing
target out before it runs (tested; fixed 1.8xATR netted 6x the ratchet).

GOLD-ONLY, M5-ONLY: declares ``scan_timeframe = "M5"`` so the scanner fetches
5-minute bars for it regardless of the global scan timeframe, and _decide_at
returns None for any asset other than GOLD.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies import indicators as ind
from app.strategies.base import Strategy

_WARMUP = 55  # need EMA50 + a little settle


class GoldM5Pullback(Strategy):
    name = "Gold M5 Pullback"
    scan_timeframe = "M5"   # the scanner uses THIS timeframe for this strategy

    def __init__(self, sl_atr: float = 1.2, rr: float = 1.5,
                 rsi_period: int = 14, atr_period: int = 14) -> None:
        self.sl_atr, self.rr = sl_atr, rr
        self.rsi_period, self.atr_period = rsi_period, atr_period

    def _series(self, df: pd.DataFrame) -> dict:
        c = df["close"]
        return {
            "close": c.to_numpy(dtype=float),
            "high": df["high"].to_numpy(dtype=float),
            "low": df["low"].to_numpy(dtype=float),
            "e9": ind.ema(c, 9).to_numpy(),
            "e21": ind.ema(c, 21).to_numpy(),
            "e50": ind.ema(c, 50).to_numpy(),
            "rsi": ind.rsi(c, self.rsi_period).to_numpy(),
            "atr": ind.atr(df, self.atr_period).to_numpy(),
        }

    def _decide_at(self, asset: str, s: dict, i: int, timeframe: str) -> Signal | None:
        if asset != "GOLD":
            return None   # gold-only edge; ignore if ever deployed elsewhere
        a = s["atr"][i]; r = s["rsi"][i]
        e9 = s["e9"][i]; e21 = s["e21"][i]; e50 = s["e50"][i]
        if any(np.isnan(x) for x in (a, r, e9, e21, e50)) or a == 0:
            return None
        c = float(s["close"][i]); h = float(s["high"][i]); l = float(s["low"][i])

        up = e9 > e21 and c > e50
        down = e9 < e21 and c < e50
        # pullback: this bar dipped to/through EMA9 and closed back the trend way
        if up and l <= e9 and c > e9 and r < 55:
            sl, tp = ind.bracket("BUY", c, a, self.sl_atr, self.rr)
            return Signal(asset, Direction.BUY, c, sl, tp, timeframe)
        if down and h >= e9 and c < e9 and r > 45:
            sl, tp = ind.bracket("SELL", c, a, self.sl_atr, self.rr)
            return Signal(asset, Direction.SELL, c, sl, tp, timeframe)
        return None

    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        if df is None or len(df) < _WARMUP:
            return None
        return self._decide_at(asset, self._series(df), len(df) - 1, timeframe)

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        n = 0 if df is None else len(df)
        out: list[Signal | None] = [None] * n
        if n < _WARMUP:
            return out
        s = self._series(df)
        for i in range(_WARMUP, n):
            out[i] = self._decide_at(asset, s, i, timeframe)
        return out
