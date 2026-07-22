"""Break-and-retest: price breaks a prior swing level, comes BACK to it, and
holds — enter on the hold, in the direction of the break. Fixed 1:2 RR.

Why retest rather than plain breakout. A naive breakout buys the bar that
clears the level, which is the worst price of the move and is what a false
break punishes hardest. Waiting for price to return to the broken level and
hold gives a tighter stop (just through the level) and a defined invalidation,
so the same target is a shorter distance in risk terms.

It also fits how this account executes. A retest entry sits BEHIND price, so
it is a genuine LIMIT order — unlike the breakout strategies that were sending
buys above market as buy-limits and being rejected with retcode 10015.

The state machine, all of it causal:

    1. level   = highest high (lowest low) of the prior `lookback` bars,
                 measured to the bar BEFORE the break so the forming bar
                 cannot define the level it breaks.
    2. break   = a close beyond that level.
    3. retest  = within `retest_window` bars, price trades back INTO the level
                 (low <= level for a break-up) but still CLOSES beyond it —
                 the level held as support/resistance.
    4. entry   = that bar's close. SL sits `sl_buffer_atr` ATR through the
                 level, so the trade is wrong exactly when the level fails.
                 TP = entry + rr x risk.
    5. abort   = a close back through the level before any retest. The break
                 failed; stop watching it.

generate() and signals() both run the same _scan(), so the live decision and
the backtested one cannot drift apart.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies.base import Strategy


class BreakRetest(Strategy):
    name = "Break & Retest"

    def __init__(self, lookback: int = 20, retest_window: int = 10,
                 atr_period: int = 14, sl_buffer_atr: float = 0.5,
                 rr: float = 2.0) -> None:
        self.lookback = lookback
        self.retest_window = retest_window
        self.atr_period = atr_period
        self.sl_buffer_atr = sl_buffer_atr
        self.rr = rr

    # ── indicators ────────────────────────────────────────────────────────
    @staticmethod
    def _atr(df: pd.DataFrame, period: int) -> pd.Series:
        hl = df["high"] - df["low"]
        hc = (df["high"] - df["close"].shift()).abs()
        lc = (df["low"] - df["close"].shift()).abs()
        return pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(period).mean()

    # ── one causal pass ───────────────────────────────────────────────────
    def _scan(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        n = 0 if df is None else len(df)
        out: list[Signal | None] = [None] * n
        need = self.lookback + self.atr_period + 2
        if n < need:
            return out

        high = df["high"].to_numpy(dtype=float)
        low = df["low"].to_numpy(dtype=float)
        close = df["close"].to_numpy(dtype=float)
        atr = self._atr(df, self.atr_period).to_numpy()
        # shift(1) — the level is defined by bars strictly BEFORE the one being
        # judged, otherwise the breaking bar helps set the level it breaks.
        res = df["high"].rolling(self.lookback).max().shift(1).to_numpy()
        sup = df["low"].rolling(self.lookback).min().shift(1).to_numpy()

        # pending break being watched for a retest
        pend_dir = 0          # +1 broke up, -1 broke down, 0 nothing pending
        pend_level = np.nan
        pend_age = 0

        for i in range(need, n):
            a = atr[i]
            if np.isnan(a) or a <= 0:
                continue

            if pend_dir != 0:
                pend_age += 1
                if pend_age > self.retest_window:
                    pend_dir = 0                      # never came back; drop it
                elif pend_dir == 1:
                    if close[i] < pend_level:
                        pend_dir = 0                  # break failed
                    elif low[i] <= pend_level and close[i] > pend_level:
                        entry = float(close[i])
                        sl = float(pend_level - self.sl_buffer_atr * a)
                        risk = entry - sl
                        if risk > 0:
                            out[i] = Signal(asset, Direction.BUY, entry,
                                            round(sl, 5),
                                            round(entry + self.rr * risk, 5),
                                            timeframe)
                            pend_dir = 0
                else:
                    if close[i] > pend_level:
                        pend_dir = 0
                    elif high[i] >= pend_level and close[i] < pend_level:
                        entry = float(close[i])
                        sl = float(pend_level + self.sl_buffer_atr * a)
                        risk = sl - entry
                        if risk > 0:
                            out[i] = Signal(asset, Direction.SELL, entry,
                                            round(sl, 5),
                                            round(entry - self.rr * risk, 5),
                                            timeframe)
                            pend_dir = 0

            # A fresh break arms the watch (only when nothing is pending, so one
            # level is tracked at a time and signals cannot stack).
            if pend_dir == 0:
                r, s = res[i], sup[i]
                if not np.isnan(r) and close[i] > r:
                    pend_dir, pend_level, pend_age = 1, float(r), 0
                elif not np.isnan(s) and close[i] < s:
                    pend_dir, pend_level, pend_age = -1, float(s), 0

        return out

    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        sigs = self._scan(asset, df, timeframe)
        return sigs[-1] if sigs else None

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        return self._scan(asset, df, timeframe)
