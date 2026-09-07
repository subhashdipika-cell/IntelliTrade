"""Immutable research snapshots and separately collected forward bars.

Run: python research_dataset.py freeze|verify|collect-forward DIRECTORY
No credentials/account identifiers are exported. No trades or setting changes.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from research_continuation import validate_bars

ROOT = Path(__file__).resolve().parent
ASSETS = ('GOLD', 'BTC')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
    paths = [ROOT / 'research_continuation.py', ROOT / 'research_dataset.py']
    paths += sorted((ROOT / 'app' / 'strategies').glob('*.py'))
    return {str(p.relative_to(ROOT)): digest(p) for p in paths}


def load_snapshot(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    result = {}
    for asset in ASSETS:
        path = directory / (asset + '.csv')
        if digest(path) != manifest['assets'][asset]['sha256']:
            raise ValueError('Snapshot hash mismatch: ' + asset)
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        validate_bars(frame)
        result[asset] = frame
    return manifest, result


def forward_subset(frame, boundary):
    validate_bars(frame)
    return frame.loc[frame.index >= pd.Timestamp(boundary)]


def freeze(directory, frames, specs, captured_at):
    directory = Path(directory)
    for frame in frames.values():
        validate_bars(frame)
    # Refuse to replace an earlier snapshot or mix files from separate runs.
    directory.mkdir(parents=True, exist_ok=False)
    manifest = dict(version=1, captured_utc=captured_at, timeframe='M30',
                    data_class='previously_inspected_development_history',
                    timestamp_basis='MT5 broker bar labels; not assumed UTC',
                    source_hashes=source_hashes(), assets={},
                    validation_policy={
                        'status': 'AWAITING_FUTURE_DATA',
                        'minimum_calendar_days': 60,
                        'minimum_closed_trades_per_asset': 30,
                        'normal_cost_pf_min': 1.2,
                        'double_spread_pf_min': 1.0,
                        'double_spread_return_must_be_positive': True,
                        'drawdown_limit_pct': 5,
                        'policy': 'No tuning on forward data. Code changes require a new freeze. No automatic promotion.'})
    for asset in ASSETS:
        frame = frames[asset]
        path = directory / (asset + '.csv')
        frame.to_csv(path, index_label='broker_time')
        # Exclude the bar that was forming at capture plus another full bar.
        boundary = frame.index[-1] + pd.Timedelta(minutes=90)
        manifest['assets'][asset] = dict(sha256=digest(path), rows=len(frame),
            first=str(frame.index[0]), last=str(frame.index[-1]),
            forward_from_broker_time=str(boundary), specification=specs[asset])
    with (directory / 'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2)
    return manifest


def collect(directory, frames):
    manifest, history = load_snapshot(directory)
    batch = {}
    counts = {}
    for asset in ASSETS:
        frame = forward_subset(frames[asset], manifest['assets'][asset]['forward_from_broker_time'])
        if frame.index.isin(history[asset].index).any():
            raise ValueError('Forward/development overlap')
        batch[asset] = frame
        counts[asset] = len(frame)
    if not any(counts.values()):
        return {'status': 'AWAITING_FUTURE_DATA', 'rows': counts}
    target = Path(directory) / 'forward' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target.mkdir(parents=True, exist_ok=False)
    files = {}
    for asset, frame in batch.items():
        path = target / (asset + '.csv')
        frame.to_csv(path, index_label='broker_time')
        files[asset] = {'rows': len(frame), 'sha256': digest(path)}
    result = dict(status='COLLECTED_NOT_VALIDATED', files=files,
                  source_unchanged=source_hashes() == manifest['source_hashes'],
                  note='Batches can overlap each other: deduplicate by broker timestamp; never count duplicate bars twice.')
    (target / 'manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['freeze','verify','collect-forward'])
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    if args.action == 'verify':
        manifest, frames = load_snapshot(args.directory)
        print(json.dumps({'status':'VERIFIED','rows':{k:len(v) for k,v in frames.items()},
                          'source_unchanged':source_hashes()==manifest['source_hashes']}))
        return
    if args.action == 'freeze' and args.directory.exists():
        raise FileExistsError('Choose a new snapshot directory')
    from app.services.mt5_client import mt5_client
    try:
        if not mt5_client.connect() or mt5_client.verify_account_type() != 'DEMO':
            raise RuntimeError('Verified DEMO connection required')
        frames = {asset:mt5_client.fetch_ohlcv(asset,'M30',10000).iloc[:-1] for asset in ASSETS}
        if args.action == 'freeze':
            specs = {asset:mt5_client.symbol_spec(asset) for asset in ASSETS}
            if any(not s for s in specs.values()):
                raise RuntimeError('Missing broker specification')
            result = freeze(args.directory, frames, specs, datetime.now(timezone.utc).isoformat())
        else:
            result = collect(args.directory, frames)
        print(json.dumps(result, indent=2))
    finally:
        mt5_client.shutdown()


if __name__ == '__main__':
    main()
