"""Turtle Soup — Connors & Raschke, *Street Smarts* (1995), the "test" archetype.

Source note: `E:/Obsidian/Trading_Mind/wiki/sources/street-smarts.md`.
"The strongest pattern in swing trading is trading on tests of previous highs
or lows."

The trade fades a FAILED breakout of an N-bar extreme. Turtle-style breakout
traders buy the new N-bar high / sell the new N-bar low; their protective stops
sit just back inside the level. When price pokes through and immediately
reclaims the level, those breakout entries are trapped and their forced covering
supplies the fuel for the reversal.

Rules (long; short is the mirror):
  1. This bar's low takes out the prior N-bar low (a genuine new extreme).
  2. The prior N-bar low was set at least ``min_age`` bars ago — the original
     rule's 4-day freshness test. A level probed again immediately has not had
     time to accumulate the resting stops the trade feeds on.
  3. The bar CLOSES back above that prior low: swept and reclaimed in one bar.
  4. Stop goes below the failed new low (very tight, by design).
  5. Target at ``rr`` × risk — Street Smarts asks for 2:1 minimum.

Timeframe: swing (D1). The pattern is timeframe-agnostic in the book (the authors
cite traders using it on 5-minute S&P charts), but on gold and crypto the higher
timeframe is what makes the spread a rounding error rather than the whole edge —
the same finding that rescued the M5 gold scalp.

*** RESEARCH ONLY — DO NOT DEPLOY. Backtest verdict (2026-07-23) ***
Tested on D1 gold/BTC/ETH net of costs across rr 1.0/1.5/2.0/3.0 and lookback
10/20/40. It failed every combination, and the 70/30 split is damning — at its
best setting (rr=3.0) the held-out window returned PF 0.00 (GOLD, 6 trades),
0.14 (BTC) and 0.33 (ETH) against in-sample 1.65 / 1.00 / 0.75. The in-sample
gold number was noise.
Kept in the registry so the negative result stays reproducible rather than being
silently re-discovered later. The likely reason it fails here: the pattern feeds
on trapped breakout traders' stops, and 24h gold/crypto do not clear resting
stops at a daily N-bar extreme the way the 1995 pit-era futures market did.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies import indicators as ind
from app.strategies.base import Strategy


class TurtleSoup(Strategy):
    name = "Turtle Soup"
    scan_timeframe = "D1"

    def __init__(self, lookback: int = 20, min_age: int = 4, rr: float = 2.0,
                 stop_buffer_atr: float = 0.10, atr_period: int = 14) -> None:
        self.lookback = lookback
        self.min_age = min_age
        self.rr = rr
        self.stop_buffer_atr = stop_buffer_atr
        self.atr_period = atr_period

    @property
    def _warmup(self) -> int:
        return self.lookback + self.atr_period + 2

    def _series(self, df: pd.DataFrame) -> dict:
        low, high = df["low"], df["high"]
        # Extremes of the N bars BEFORE the current bar. shift(1) keeps the
        # current bar out of its own reference level, which is the whole point:
        # the bar must break a level that already existed.
        return {
            "open": df["open"].to_numpy(dtype=float),
            "high": high.to_numpy(dtype=float),
            "low": low.to_numpy(dtype=float),
            "close": df["close"].to_numpy(dtype=float),
            "prior_low": low.rolling(self.lookback).min().shift(1).to_numpy(),
            "prior_high": high.rolling(self.lookback).max().shift(1).to_numpy(),
            # Bars since that extreme was set (freshness / min_age test).
            "low_age": low.rolling(self.lookback).apply(
                lambda w: len(w) - 1 - int(np.argmin(w)), raw=True
            ).shift(1).to_numpy(),
            "high_age": high.rolling(self.lookback).apply(
                lambda w: len(w) - 1 - int(np.argmax(w)), raw=True
            ).shift(1).to_numpy(),
            "atr": ind.atr(df, self.atr_period).to_numpy(),
        }

    def _decide_at(self, asset: str, s: dict, i: int, timeframe: str) -> Signal | None:
        a = s["atr"][i]
        prior_low, prior_high = s["prior_low"][i], s["prior_high"][i]
        low_age, high_age = s["low_age"][i], s["high_age"][i]
        if any(np.isnan(x) for x in (a, prior_low, prior_high, low_age, high_age)) or a <= 0:
            return None
        c = float(s["close"][i])
        h = float(s["high"][i])
        low_i = float(s["low"][i])
        buf = self.stop_buffer_atr * a

        # Long: swept the prior N-bar low and closed back above it.
        if low_i < prior_low and c > prior_low and low_age >= self.min_age:
            sl = round(low_i - buf, 5)
            risk = c - sl
            if risk > 0:
                return Signal(asset, Direction.BUY, c, sl, round(c + self.rr * risk, 5), timeframe)

        # Short: swept the prior N-bar high and closed back below it.
        if h > prior_high and c < prior_high and high_age >= self.min_age:
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
