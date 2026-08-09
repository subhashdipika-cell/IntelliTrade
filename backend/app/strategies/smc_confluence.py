"""Causal SMC + OB + FVG + Hull + UT confluence strategy.

This is a native IntelliTrade implementation of the supplied rule set.  Every
decision is made on a completed candle; order blocks and FVGs are stored only
after the BOS/FVG candle exists, so no future price is used.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies.base import Strategy


class SmcConfluence(Strategy):
    name = "SMC OB FVG Hull UT Confluence"
    scan_timeframe = "M5"

    def __init__(self, hull_length: int = 55, ut_key_value: float = 1.0,
                 ut_atr_period: int = 10, structure_length: int = 3,
                 ob_lookback: int = 8, zone_expiry: int = 30,
                 near_atr: float = 0.30, sl_buffer_atr: float = 0.20,
                 rr: float = 2.0, max_risk_atr: float = 3.0) -> None:
        self.hull_length = hull_length
        self.ut_key_value = ut_key_value
        self.ut_atr_period = ut_atr_period
        self.structure_length = structure_length
        self.ob_lookback = ob_lookback
        self.zone_expiry = zone_expiry
        self.near_atr = near_atr
        self.sl_buffer_atr = sl_buffer_atr
        self.rr = rr
        self.max_risk_atr = max_risk_atr

    @staticmethod
    def _wma(series: pd.Series, length: int) -> pd.Series:
        weights = np.arange(1, length + 1, dtype=float)
        return series.rolling(length).apply(lambda x: float(np.dot(x, weights) / weights.sum()), raw=True)

    def _hull(self, close: pd.Series) -> pd.Series:
        half = max(2, self.hull_length // 2)
        root = max(2, int(math.sqrt(self.hull_length)))
        return self._wma(2 * self._wma(close, half) - self._wma(close, self.hull_length), root)

    @staticmethod
    def _atr(df: pd.DataFrame, period: int) -> pd.Series:
        prev = df["close"].shift(1)
        tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def _ut_position(self, close: np.ndarray, atr: np.ndarray) -> np.ndarray:
        pos = np.zeros(len(close), dtype=int)
        stop = np.full(len(close), np.nan)
        current = np.nan
        state = 0
        for i, price in enumerate(close):
            if not np.isfinite(atr[i]) or atr[i] <= 0:
                stop[i] = current
                pos[i] = state
                continue
            loss = self.ut_key_value * atr[i]
            if not np.isfinite(current):
                current = price - loss
                stop[i] = current
                pos[i] = state
                continue
            previous_price = close[i - 1]
            previous_stop = current
            if price > previous_stop and previous_price > previous_stop:
                current = max(previous_stop, price - loss)
            elif price < previous_stop and previous_price < previous_stop:
                current = min(previous_stop, price + loss)
            else:
                current = price - loss if price > previous_stop else price + loss
            if previous_price <= previous_stop < price:
                state = 1
            elif previous_price >= previous_stop > price:
                state = -1
            stop[i] = current
            pos[i] = state
        return pos

    @staticmethod
    def _in_or_near(price: float, low: float, high: float, tolerance: float) -> bool:
        return low - tolerance <= price <= high + tolerance

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        n = 0 if df is None else len(df)
        out: list[Signal | None] = [None] * n
        warmup = max(self.hull_length + 10, self.ut_atr_period + 5, 40)
        if n < warmup:
            return out
        work = df.sort_index()
        o = work["open"].to_numpy(dtype=float)
        h = work["high"].to_numpy(dtype=float)
        l = work["low"].to_numpy(dtype=float)
        c = work["close"].to_numpy(dtype=float)
        atr = self._atr(work, self.ut_atr_period).to_numpy(dtype=float)
        hull = self._hull(work["close"]).to_numpy(dtype=float)
        ut = self._ut_position(c, atr)
        prior_high = work["high"].rolling(self.structure_length).max().shift(1).to_numpy()
        prior_low = work["low"].rolling(self.structure_length).min().shift(1).to_numpy()

        bullish_ob: tuple[float, float, int] | None = None
        bearish_ob: tuple[float, float, int] | None = None
        bullish_fvg: tuple[float, float, int] | None = None
        bearish_fvg: tuple[float, float, int] | None = None
        trend = 0

        for i in range(warmup, n):
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue
            bullish_bos = np.isfinite(prior_high[i]) and c[i] > prior_high[i]
            bearish_bos = np.isfinite(prior_low[i]) and c[i] < prior_low[i]
            if bullish_bos:
                trend = 1
                for j in range(i - 1, max(warmup, i - self.ob_lookback) - 1, -1):
                    if c[j] < o[j]:
                        bullish_ob = (float(l[j]), float(h[j]), i)
                        break
            elif bearish_bos:
                trend = -1
                for j in range(i - 1, max(warmup, i - self.ob_lookback) - 1, -1):
                    if c[j] > o[j]:
                        bearish_ob = (float(l[j]), float(h[j]), i)
                        break

            if i >= 2 and l[i] > h[i - 2]:
                bullish_fvg = (float(h[i - 2]), float(l[i]), i)
            if i >= 2 and h[i] < l[i - 2]:
                bearish_fvg = (float(h[i]), float(l[i - 2]), i)

            if bullish_ob and i - bullish_ob[2] > self.zone_expiry:
                bullish_ob = None
            if bearish_ob and i - bearish_ob[2] > self.zone_expiry:
                bearish_ob = None
            if bullish_fvg and i - bullish_fvg[2] > self.zone_expiry:
                bullish_fvg = None
            if bearish_fvg and i - bearish_fvg[2] > self.zone_expiry:
                bearish_fvg = None

            # UT state changes and Hull slope are evaluated on this closed bar.
            ut_buy = ut[i] == 1 and ut[i - 1] != 1
            ut_sell = ut[i] == -1 and ut[i - 1] != -1
            hull_up = np.isfinite(hull[i]) and np.isfinite(hull[i - 1]) and hull[i] > hull[i - 1]
            hull_down = np.isfinite(hull[i]) and np.isfinite(hull[i - 1]) and hull[i] < hull[i - 1]
            bullish_zone = bullish_ob and bullish_fvg and self._in_or_near(c[i], bullish_ob[0], bullish_ob[1], self.near_atr * a) and self._in_or_near(c[i], bullish_fvg[0], bullish_fvg[1], self.near_atr * a)
            bearish_zone = bearish_ob and bearish_fvg and self._in_or_near(c[i], bearish_ob[0], bearish_ob[1], self.near_atr * a) and self._in_or_near(c[i], bearish_fvg[0], bearish_fvg[1], self.near_atr * a)

            if bullish_zone and trend == 1 and ut_buy and hull_up:
                sl = min(bullish_ob[0], l[i]) - self.sl_buffer_atr * a
                risk = c[i] - sl
                if 0 < risk <= self.max_risk_atr * a:
                    out[i] = Signal(asset, Direction.BUY, float(c[i]), round(float(sl), 5), round(float(c[i] + self.rr * risk), 5), timeframe)
            elif bearish_zone and trend == -1 and ut_sell and hull_down:
                sl = max(bearish_ob[1], h[i]) + self.sl_buffer_atr * a
                risk = sl - c[i]
                if 0 < risk <= self.max_risk_atr * a:
                    out[i] = Signal(asset, Direction.SELL, float(c[i]), round(float(sl), 5), round(float(c[i] - self.rr * risk), 5), timeframe)
        return out

    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        signals = self.signals(asset, df, timeframe)
        return signals[-1] if signals else None
