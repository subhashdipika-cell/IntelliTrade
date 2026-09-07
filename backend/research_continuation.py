"""Read-only chronological comparison; no orders or settings changes.

Bid OHLC; next-open adverse spread/slippage on entry, ask-adjusted SELL exits,
stop-first ambiguous candles, adverse stop gaps, no favorable target gaps,
broker volume steps/caps, mark-to-market drawdown and forced end liquidation.
Swap is not modeled. Fixed spreads cannot reproduce real tick execution.
"""
import json
import math
from pathlib import Path
import numpy as np

from app.services.mt5_client import mt5_client
from app.strategies.continuation_research import GoldContinuation, BtcContinuation
from app.strategies.demo_m30_trend import GoldM30Trend, BtcM30Trend


def validate_bars(df):
    if df.empty or not df.index.is_monotonic_increasing or df.index.has_duplicates or df.index.hasnans:
        raise ValueError('Bars must have a nonempty, ordered, unique timestamp index')
    prices = df[['open', 'high', 'low', 'close']]
    if not np.isfinite(prices.to_numpy(dtype=float)).all() or (prices <= 0).any().any():
        raise ValueError('OHLC prices must be finite and positive')
    if ((df.high < prices.max(axis=1)) | (df.low > prices.min(axis=1))).any():
        raise ValueError('Invalid OHLC range')


def resolve_exit(side, sl, tp, op, hi, lo, slip):
    # The open is known to precede the intrabar extremes. A gap through a
    # target exits before a later stop touch; ambiguous intrabar touches use SL.
    if side*(op-sl) <= 0:
        return op-side*slip, 'gap_stop'
    if side*(op-tp) >= 0:
        return tp, 'gap_target'
    if (side == 1 and lo <= sl) or (side == -1 and hi >= sl):
        return sl-side*slip, 'stop'
    if (side == 1 and hi >= tp) or (side == -1 and lo <= tp):
        return tp, 'target'
    return None, None


def simulate(df, signals, spec, asset, start, end, multiplier):
    validate_bars(df)
    if len(signals) != len(df) or not 0 <= start < end <= len(df):
        raise ValueError('Signals and split boundaries must align with bars')
    if asset not in ('GOLD', 'BTC') or multiplier <= 0 or not math.isfinite(multiplier):
        raise ValueError('Unsupported asset or invalid spread multiplier')
    for key in ('trade_tick_value_loss','trade_tick_size','volume_step','volume_min','volume_max','point','bid','ask'):
        if not math.isfinite(spec[key]) or spec[key] <= 0:
            raise ValueError('Invalid broker specification: ' + key)
    if spec['ask'] < spec['bid'] or spec['volume_min'] > spec['volume_max']:
        raise ValueError('Invalid spread or volume bounds')
    balance = peak = 10000.0
    drawdown = 0.0
    pos = None
    pnls = []
    ledger = []
    spread = (spec['ask'] - spec['bid']) * multiplier
    slip = max(spec['point'], spread * .1)
    value = spec['trade_tick_value_loss'] / spec['trade_tick_size']
    commission = 6 if asset == 'GOLD' else 0  # assumed round trip per lot
    cap = .05 if asset == 'GOLD' else .2
    rejected = 0

    def settle(price):
        return (price-pos['entry'])*pos['side']*pos['lots']*value - commission*pos['lots']

    for i in range(start, end):
        bar = df.iloc[i]
        if pos is None and i > start:
            signal = signals[i-1]
            if signal is not None:
                side = 1 if signal.direction.value == 'BUY' else -1
                entry = float(bar.open) + (spread if side == 1 else 0) + side*slip
                risk = side*(entry-signal.stop_loss)
                reward = side*(signal.target-entry)
                if risk > 0 and reward/risk >= 1.5:
                    budget = balance*.005
                    lots = min(cap, spec['volume_max'], budget/((risk+slip)*value+commission))
                    lots = math.floor(lots/spec['volume_step'] + 1e-9)*spec['volume_step']
                    if lots >= spec['volume_min']:
                        pos = dict(entry=entry, side=side, lots=lots, sl=signal.stop_loss, tp=signal.target,
                                   signal_time=str(df.index[i-1]), entry_time=str(df.index[i]))
                    else:
                        rejected += 1
        if pos:
            side = pos['side']
            adjustment = spread if side == -1 else 0
            op, hi, lo = (float(bar[k])+adjustment for k in ['open','high','low'])
            price, reason = resolve_exit(side, pos['sl'], pos['tp'], op, hi, lo, slip)
            if price is None and i == end-1:
                price = float(bar.close)+adjustment-side*slip
                reason = 'end_liquidation'
            if price is not None:
                pnl = settle(price)
                balance += pnl
                pnls.append(pnl)
                ledger.append({**pos, 'exit': price, 'exit_time': str(df.index[i]),
                               'reason': reason, 'net_pnl': pnl})
                pos = None
        equity = balance + (settle(float(bar.close)+(spread if pos['side'] == -1 else 0)) if pos else 0)
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak-equity)/peak*100)
    wins = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    return dict(trades=len(pnls), return_pct=round((balance/10000-1)*100,3),
                profit_factor=round(wins/losses,3) if losses else None,
                win_rate=round(sum(p>0 for p in pnls)/len(pnls)*100,2) if pnls else None,
                max_drawdown_pct=round(drawdown,3), minimum_lot_rejections=rejected,
                simulator_version=2, ledger=ledger)


def main(pairs=None, report_name='continuation_research_2026-09-07.json', snapshot=None):
    if pairs is None:
        pairs = [('GOLD', GoldContinuation(), GoldM30Trend()), ('BTC', BtcContinuation(), BtcM30Trend())]
    frozen = None
    if snapshot is not None:
        from research_dataset import load_snapshot
        manifest, frozen = load_snapshot(snapshot)
    elif not mt5_client.connect() or mt5_client.verify_account_type() != 'DEMO':
        mt5_client.shutdown()
        raise RuntimeError('Research requires DEMO data connection')
    report = {'design': 'Fixed rules; 50% development, 25% validation, 25% holdout. No optimization.',
              'limitations': 'Swap/funding and live trailing/news filters excluded; historical bid OHLC, current contract specs and fixed spread assumptions. Holdout is not fresh unseen forward data.',
              'gate': 'Validation and holdout each >=20 closed trades, PF >=1.2 at 1x, PF >=1 at 2x, DD <=5%, plus positive return; no promotion based on frequency alone.',
              'assets': {}}
    if frozen is not None:
        report['snapshot'] = manifest
    report['simulator_version'] = 2
    try:
        for asset, candidate, baseline in pairs:
            df = frozen[asset] if frozen is not None else mt5_client.fetch_ohlcv(asset, 'M30', 10000).iloc[:-1]
            if len(df)<4000 or not df.index.is_monotonic_increasing or df.index.has_duplicates:
                raise RuntimeError('Insufficient or malformed data')
            spec = manifest['assets'][asset]['specification'] if frozen is not None else mt5_client.symbol_spec(asset)
            if not spec or spec['trade_tick_value_loss'] <= 0 or spec['trade_tick_size'] <= 0:
                raise RuntimeError('Invalid broker contract specification')
            n = len(df)
            results = {}
            for label, strategy in [('candidate',candidate),('baseline',baseline)]:
                signals = strategy.signals(asset,df,'M30')
                results[label] = {}
                for split, start, end in [('development',110,n//2),('validation',n//2,3*n//4),('holdout',3*n//4,n)]:
                    results[label][split] = {str(cost):simulate(df,signals,spec,asset,start,end,cost) for cost in (1,2)}
            passed = all(results['candidate'][part]['1']['trades'] >= 20
                         and (results['candidate'][part]['1']['profit_factor'] or 0) >= 1.2
                         and (results['candidate'][part]['2']['profit_factor'] or 0) >= 1
                         and results['candidate'][part]['2']['return_pct'] > 0
                         and results['candidate'][part]['2']['max_drawdown_pct'] <= 5
                         for part in ['validation','holdout'])
            report['assets'][asset] = dict(start=str(df.index[0]),end=str(df.index[-1]), bars=n,
                                          eligible=passed,results=results)
        (Path(__file__).resolve().parent.parent / 'docs' / report_name).write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({'report': report_name, 'eligible': {k:v['eligible'] for k,v in report['assets'].items()}},indent=2))
    finally:
        if frozen is None:
            mt5_client.shutdown()


if __name__ == '__main__':
    main()
