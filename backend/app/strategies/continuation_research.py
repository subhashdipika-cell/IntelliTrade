"""Fixed-rule continuation candidates. Research only until independently approved.

Finite rolling windows make replay and the scanner's 500-bar window identical.
No future bars, broker-clock conversion, or discretionary levels are used.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies.base import Strategy
from app.strategies.sma_crossover import SmaCrossover


class _Continuation(Strategy):
    research_only = True
    scan_timeframe = 'M30'
    scan_lookback = 500
    asset = ''
    trend_period = 60
    stop_atr = 1.5
    reward = 2.0

    def generate(self, asset, df, timeframe):
        signals = self.signals(asset, df, timeframe)
        return signals[-1] if signals else None

    def signals(self, asset, df, timeframe):
        n = 0 if df is None else len(df)
        out = [None] * n
        if asset != self.asset or timeframe != self.scan_timeframe or n < 110:
            return out
        close = df.close.to_numpy(float)
        high = df.high.to_numpy(float)
        low = df.low.to_numpy(float)
        fast = df.close.rolling(20).mean().to_numpy()
        trend = df.close.rolling(self.trend_period).mean().to_numpy()
        atr = SmaCrossover._atr(df, 14).to_numpy()
        normal = pd.Series(atr).rolling(80).median().to_numpy()
        volume = df.tick_volume.to_numpy(float) if 'tick_volume' in df else np.zeros(n)
        volume_mean = pd.Series(volume).rolling(20).mean().to_numpy()
        for i in range(110, n):
            a = atr[i]
            # Avoid dead volatility and shock candles. Slope must clear noise.
            if not np.isfinite(a) or a <= 0 or not .65 <= a / normal[i] <= 1.8:
                continue
            if high[i] - low[i] > 2 * a:
                continue
            for side in (1, -1):
                if side * (fast[i] - trend[i]) <= .15 * a:
                    continue
                if side * (trend[i] - trend[i-5]) <= .05 * a:
                    continue
                if self.asset == 'GOLD':
                    # Previous candle pulled through SMA20; reclaim must also
                    # break its high/low. This is an event, not a standing trend.
                    touched = low[i-1] <= fast[i-1] if side == 1 else high[i-1] >= fast[i-1]
                    reclaimed = side * (close[i-1] - fast[i-1]) <= 0 < side * (close[i] - fast[i])
                    broke = close[i] > high[i-1] if side == 1 else close[i] < low[i-1]
                    confirmed = touched and reclaimed and broke
                else:
                    # BTC resumes after a three-bar countertrend pause, with
                    # above-average broker tick activity (not exchange volume).
                    pause = side * (close[i-1] - close[i-4]) < 0
                    broke = close[i] > max(high[i-3:i]) if side == 1 else close[i] < min(low[i-3:i])
                    confirmed = pause and broke and volume[i] > volume_mean[i]
                if not confirmed or side * (close[i] - fast[i]) > 1.5 * a:
                    continue
                swing = min(low[i-3:i+1]) - .15*a if side == 1 else max(high[i-3:i+1]) + .15*a
                distance = max(self.stop_atr*a, side*(close[i]-swing))
                if distance > 2.5*a:
                    continue
                out[i] = Signal(asset, Direction.BUY if side == 1 else Direction.SELL,
                                float(close[i]), float(close[i]-side*distance),
                                float(close[i]+side*self.reward*distance), timeframe)
                break
        return out


class GoldContinuation(_Continuation):
    name = 'Gold Continuation Research'
    asset = 'GOLD'


class BtcContinuation(_Continuation):
    name = 'BTC Continuation Research'
    asset = 'BTC'
    trend_period = 80
    stop_atr = 1.8
    reward = 2.2
