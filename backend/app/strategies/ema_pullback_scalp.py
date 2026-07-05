"""EMA pullback SCALP — tuned for Gold on 1-5 minute charts with FIXED pip-based
stops/targets (not ATR).

Entry: same idea as EMA Pullback — trade with the fast/slow trend when price
reclaims the fast EMA after a pullback — but with faster EMAs (9/21/50) suited to
M1/M5, and a fixed SL/TP measured in PIPS.

Pip size is configurable because Gold has no universal pip:
  pip_size = 0.01  → 500 pips = $5  SL, 1000-1500 pips = $10-15 TP  (scalp-fitting)
  pip_size = 0.10  → 500 pips = $50 SL, 1000-1500 pips = $100-150 TP

Defaults: sl_pips=500, tp_pips=1500 (i.e. 3:1 — best of the 1000-1500 range in
backtests so far), pip_size=0.01.
"""
from __future__ import annotations

import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies import indicators as ind
from app.strategies.base import Strategy


class EmaPullbackScalp(Strategy):
    name = "EMA Pullback Scalp"

    def __init__(self, fast: int = 9, mid: int = 21, slow: int = 50,
                 sl_pips: float = 500, tp_pips: float = 1500,
                 pip_size: float = 0.01) -> None:
        self.fast, self.mid, self.slow = fast, mid, slow
        self.sl_pips, self.tp_pips, self.pip_size = sl_pips, tp_pips, pip_size

    def _series(self, df: pd.DataFrame) -> dict:
        close = df["close"]
        return {
            "close": close.to_numpy(dtype=float),
            "e_fast": ind.ema(close, self.fast).to_numpy(),
            "e_mid": ind.ema(close, self.mid).to_numpy(),
            "e_slow": ind.ema(close, self.slow).to_numpy(),
        }

    def _decide_at(self, asset: str, s: dict, i: int, timeframe: str) -> Signal | None:
        price = float(s["close"][i])
        prev = float(s["close"][i - 1])
        uptrend = s["e_mid"][i] > s["e_slow"][i]
        downtrend = s["e_mid"][i] < s["e_slow"][i]
        reclaim_up = prev < s["e_fast"][i - 1] and price > s["e_fast"][i]
        reclaim_dn = prev > s["e_fast"][i - 1] and price < s["e_fast"][i]

        sl_dist = self.sl_pips * self.pip_size
        tp_dist = self.tp_pips * self.pip_size
        if uptrend and reclaim_up:
            return Signal(asset, Direction.BUY, price,
                          round(price - sl_dist, 5), round(price + tp_dist, 5), timeframe)
        if downtrend and reclaim_dn:
            return Signal(asset, Direction.SELL, price,
                          round(price + sl_dist, 5), round(price - tp_dist, 5), timeframe)
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
