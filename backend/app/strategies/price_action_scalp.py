"""Price-action scalp strategy: break, retest, rejection.

This is a machine-readable approximation of discretionary chart reading. It uses
only OHLC price action for the setup; ATR is used only to normalize the stop and
to reject abnormally large risk. The strategy waits for a prior range break,
then requires a retest that holds and a rejection candle before entering.

The same causal scan powers live generation and backtests, so a signal never
uses future bars. It is intentionally not enabled for live scanning by default;
deploy it in ``alert_only`` mode first and promote it only after walk-forward
testing on the intended symbol and timeframe.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies import indicators as ind
from app.strategies.base import Strategy


class PriceActionScalp(Strategy):
    name = "Price Action Scalp"
    scan_timeframe = "M5"

    def __init__(
        self,
        lookback: int = 20,
        retest_window: int = 4,
        atr_period: int = 14,
        retest_atr: float = 0.20,
        break_atr: float = 0.10,
        close_location: float = 0.75,
        retest_close_atr: float = 0.05,
        sl_atr: float = 0.70,
        rr: float = 1.8,
        min_body_atr: float = 0.35,
        wick_to_body: float = 0.8,
        max_risk_atr: float = 2.5,
    ) -> None:
        self.lookback = lookback
        self.retest_window = retest_window
        self.atr_period = atr_period
        self.retest_atr = retest_atr
        self.break_atr = break_atr
        self.close_location = close_location
        self.retest_close_atr = retest_close_atr
        self.sl_atr = sl_atr
        self.rr = rr
        self.min_body_atr = min_body_atr
        self.wick_to_body = wick_to_body
        self.max_risk_atr = max_risk_atr

    @staticmethod
    def _atr(df: pd.DataFrame, period: int) -> np.ndarray:
        return ind.atr(df, period).to_numpy(dtype=float)

    def _scan(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        n = 0 if df is None else len(df)
        out: list[Signal | None] = [None] * n
        need = self.lookback + self.atr_period + 2
        if n < need:
            return out

        high = df["high"].to_numpy(dtype=float)
        low = df["low"].to_numpy(dtype=float)
        open_ = df["open"].to_numpy(dtype=float)
        close = df["close"].to_numpy(dtype=float)
        atr = self._atr(df, self.atr_period)
        prior_high = df["high"].rolling(self.lookback).max().shift(1).to_numpy()
        prior_low = df["low"].rolling(self.lookback).min().shift(1).to_numpy()

        pending = 0
        level = np.nan
        age = 0

        for i in range(need, n):
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue

            body = abs(close[i] - open_[i])
            if pending:
                age += 1
                if age > self.retest_window:
                    pending = 0
                else:
                    tolerance = self.retest_atr * a
                    if pending == 1:
                        body_ok = close[i] > open_[i] and body >= self.min_body_atr * a
                        retest = (low[i] <= level + tolerance
                                  and close[i] > level + self.retest_close_atr * a)
                        lower_wick = min(open_[i], close[i]) - low[i]
                        rejection = lower_wick >= self.wick_to_body * max(body, a * 0.05)
                        if retest and body_ok and rejection:
                            sl = level - self.sl_atr * a
                            risk = close[i] - sl
                            if 0 < risk <= self.max_risk_atr * a:
                                out[i] = Signal(
                                    asset, Direction.BUY, float(close[i]),
                                    round(float(sl), 5),
                                    round(float(close[i] + self.rr * risk), 5),
                                    timeframe,
                                )
                                pending = 0
                        elif close[i] < level - tolerance:
                            pending = 0
                    else:
                        body_ok = close[i] < open_[i] and body >= self.min_body_atr * a
                        retest = (high[i] >= level - tolerance
                                  and close[i] < level - self.retest_close_atr * a)
                        upper_wick = high[i] - max(open_[i], close[i])
                        rejection = upper_wick >= self.wick_to_body * max(body, a * 0.05)
                        if retest and body_ok and rejection:
                            sl = level + self.sl_atr * a
                            risk = sl - close[i]
                            if 0 < risk <= self.max_risk_atr * a:
                                out[i] = Signal(
                                    asset, Direction.SELL, float(close[i]),
                                    round(float(sl), 5),
                                    round(float(close[i] - self.rr * risk), 5),
                                    timeframe,
                                )
                                pending = 0
                        elif close[i] > level + tolerance:
                            pending = 0

            if pending == 0:
                bar_range = high[i] - low[i]
                close_pos = ((close[i] - low[i]) / bar_range
                             if bar_range > 0 else 0.5)
                bullish_break = (
                    np.isfinite(prior_high[i])
                    and close[i] > prior_high[i] + self.break_atr * a
                    and close_pos >= self.close_location
                )
                bearish_break = (
                    np.isfinite(prior_low[i])
                    and close[i] < prior_low[i] - self.break_atr * a
                    and close_pos <= 1.0 - self.close_location
                )
                if bullish_break:
                    pending, level, age = 1, float(prior_high[i]), 0
                elif bearish_break:
                    pending, level, age = -1, float(prior_low[i]), 0

        return out

    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        sigs = self._scan(asset, df, timeframe)
        return sigs[-1] if sigs else None

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        return self._scan(asset, df, timeframe)
