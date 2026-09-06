"""Read-only MT5 signal/filter comparison. Never imports execution stages."""
import copy
import json
from collections import Counter
from pathlib import Path

from app.services.mt5_client import mt5_client
from app.strategies.demo_m30_trend import GoldM30Trend, BtcM30Trend
from app.pipeline.stages.strategy import StrategyStage
from app.pipeline.context import TradeContext
from app.backtest.engine import run_backtest


class FixedSignals:
    def __init__(self, signals):
        self.items = signals

    def signals(self, *args):
        return copy.deepcopy(self.items)


def main():
    if not mt5_client.connect():
        raise RuntimeError('MT5 unavailable; research stopped')
    report = {}
    try:
        for asset, strategy in [('GOLD', GoldM30Trend()), ('BTC', BtcM30Trend())]:
            df = mt5_client.fetch_ohlcv(asset, 'M30', 10000).iloc[:-1]
            if len(df) < 1000:
                raise RuntimeError('Insufficient historical bars')
            raw = strategy.signals(asset, df, 'M30')
            filtered = [None] * len(df)
            reasons = Counter()
            for i, sig in enumerate(raw):
                if sig is None:
                    continue
                ctx = TradeContext(asset, 'M30', signal=copy.deepcopy(sig), market_data=df.iloc[max(0, i-498):i+1])
                stage = StrategyStage(strategy)
                stage._cap_target_to_structure(ctx)
                stage._human_touch(ctx)
                if ctx.blocked:
                    reasons[ctx.decisions[-1].reason.split(' → ')[0].split(' | ')[0]] += 1
                else:
                    filtered[i] = ctx.signal
            spec = mt5_client.symbol_spec(asset)
            spread = spec['ask'] - spec['bid']
            cases = {}
            next_open = copy.deepcopy(raw)
            for i, sig in enumerate(next_open):
                if sig is None:
                    continue
                if i + 1 == len(df):
                    next_open[i] = None
                    continue
                sig.entry = float(df['open'].iloc[i+1])
                if not min(sig.stop_loss, sig.target) < sig.entry < max(sig.stop_loss, sig.target):
                    next_open[i] = None
            for label, signals in [('raw', raw), ('next_open', next_open), ('live_structure', filtered)]:
                for cost in [1, 2]:
                    cases[f'{label}_{cost}x_spread'] = run_backtest(
                        df, FixedSignals(signals), asset, risk_per_trade=.005,
                        spread=spread*cost, commission_per_lot=3 if asset == 'GOLD' else 0,
                        timeframe='M30').metrics
            report[asset] = dict(bars=len(df), start=str(df.index[0]), end=str(df.index[-1]),
                                 signals=sum(s is not None for s in raw),
                                 passed=sum(s is not None for s in filtered),
                                 spread=spread, rejections=dict(reasons), results=cases)
        dest = Path('..') / 'docs' / 'filter_audit_2026-09-07.json'
        dest.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({k: {x:v for x,v in d.items() if x != 'rejections'} for k,d in report.items()}, indent=2))
    finally:
        mt5_client.shutdown()


if __name__ == '__main__':
    main()
