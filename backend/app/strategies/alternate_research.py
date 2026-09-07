"""Pre-specified alternatives: Gold range rejection, BTC squeeze breakout.

These are hypotheses, not proven edges. Always research-only in the pipeline.
All windows use completed bars and have finite history for scanner parity.
"""
import numpy as np

from app.pipeline.context import Direction, Signal
from app.strategies.base import Strategy
from app.strategies.sma_crossover import SmaCrossover


class _Research(Strategy):
    research_only = True
    scan_timeframe = 'M30'
    scan_lookback = 500
    asset = ''

    def generate(self, asset, df, timeframe):
        items = self.signals(asset, df, timeframe)
        return items[-1] if items else None

    def _valid(self, asset, df, timeframe):
        return df is not None and len(df) >= 110 and asset == self.asset and timeframe == 'M30'


class GoldRangeReversal(_Research):
    name = 'Gold Range Reversal Research'
    asset = 'GOLD'

    def signals(self, asset, df, timeframe):
        out = [None] * (0 if df is None else len(df))
        if not self._valid(asset, df, timeframe):
            return out
        mean = df.close.rolling(20).mean().to_numpy()
        sigma = df.close.rolling(20).std(ddof=0).to_numpy()
        atr = SmaCrossover._atr(df, 14).to_numpy()
        efficiency = (df.close.diff(20).abs() / df.close.diff().abs().rolling(20).sum()).to_numpy()
        c, lo, hi = (df[k].to_numpy(float) for k in ('close','low','high'))
        for i in range(110,len(df)):
            a = atr[i]
            if not np.isfinite(a) or a <= 0 or not np.isfinite(efficiency[i]) or efficiency[i] > .3:
                continue
            if hi[i]-lo[i] > 2*a:
                continue
            # Return inside the prior bar's two-sigma range after an excursion.
            for side in (1,-1):
                band = mean[i-1]-side*2*sigma[i-1]
                if not side*(c[i-1]-band) < 0 < side*(c[i]-band):
                    continue
                stop = min(lo[i-1:i+1])-.2*a if side == 1 else max(hi[i-1:i+1])+.2*a
                risk = max(.8*a, side*(c[i]-stop))
                reward = side*(mean[i]-c[i])
                if risk > 2*a or reward/risk < 1.5:
                    continue
                out[i] = Signal(asset,Direction.BUY if side==1 else Direction.SELL,
                                float(c[i]),float(c[i]-side*risk),float(mean[i]),timeframe)
                break
        return out


class BtcSqueezeBreakout(_Research):
    name = 'BTC Squeeze Breakout Research'
    asset = 'BTC'

    def signals(self, asset, df, timeframe):
        out = [None] * (0 if df is None else len(df))
        if not self._valid(asset, df, timeframe):
            return out
        atr = SmaCrossover._atr(df,14)
        normal = atr.rolling(80).median().to_numpy()
        a = atr.to_numpy()
        upper = df.high.rolling(20).max().shift(1).to_numpy()
        lower = df.low.rolling(20).min().shift(1).to_numpy()
        c, lo, hi = (df[k].to_numpy(float) for k in ('close','low','high'))
        for i in range(110,len(df)):
            if not np.isfinite(a[i]) or a[i] <= 0 or not np.isfinite(normal[i-1]) or normal[i-1] <= 0:
                continue
            if a[i-1]/normal[i-1] > .9 or not .8*a[i] <= hi[i]-lo[i] <= 2*a[i]:
                continue
            for side in (1,-1):
                boundary = upper[i] if side == 1 else lower[i]
                if not side*(c[i-1]-boundary) <= 0 < side*(c[i]-boundary):
                    continue
                # Close in the outer quarter of the breakout candle.
                if (hi[i]-c[i] if side == 1 else c[i]-lo[i]) > .25*(hi[i]-lo[i]):
                    continue
                risk = 1.5*a[i]
                out[i] = Signal(asset,Direction.BUY if side==1 else Direction.SELL,
                                float(c[i]),float(c[i]-side*risk),float(c[i]+side*2.5*risk),timeframe)
                break
        return out
