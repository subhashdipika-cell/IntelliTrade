"""Reproducible broker-data backtest for EMA ATR ADX Trend Signals.

Read-only: connects to the configured MT5 terminal, requires a verified DEMO
account, downloads completed bars, and prints JSON. It never builds an execution
pipeline or places an order.
"""
from __future__ import annotations

import json

import MetaTrader5 as mt5

from app.backtest.engine import run_backtest
from app.backtest.walk_forward import walk_forward
from app.core.constants import (
    SUPPORTED_ASSETS,
    default_commission_per_lot,
    to_terminal_symbol,
)
from app.services.mt5_client import mt5_client
from app.strategies.ema_atr_adx_trend import EmaAtrAdxTrend


TIMEFRAMES = ("M5", "M15", "H1")
TARGET_VARIANTS = (1.5, 2.5)
BAR_COUNT = 10_000
INITIAL_CAPITAL = 1_000.0
RISK_PER_TRADE = 0.01


def main() -> None:
    if not mt5_client.connect():
        raise SystemExit("MT5 connection failed")
    verified = mt5_client.verify_account_type()
    if verified != "DEMO":
        raise SystemExit(f"Backtest requires verified DEMO terminal; got {verified!r}")

    report: dict = {
        "scope": "HISTORICAL_BACKTEST_ONLY",
        "account_type": verified,
        "bars_requested": BAR_COUNT,
        "initial_capital": INITIAL_CAPITAL,
        "risk_per_trade": RISK_PER_TRADE,
        "execution_note": "Signal close entry; fixed current spread; stop-first ambiguous bars.",
        "results": {},
    }
    for asset in SUPPORTED_ASSETS:
        report["results"][asset] = {}
        symbol = to_terminal_symbol(asset)
        info = mt5.symbol_info(symbol)
        spread = float(info.spread * info.point) if info is not None else 0.0
        commission = default_commission_per_lot(asset)
        for timeframe in TIMEFRAMES:
            frame = mt5_client.fetch_ohlcv(asset, timeframe, BAR_COUNT)
            # copy_rates_from_pos includes the forming bar at position zero.
            frame = frame.iloc[:-1] if frame is not None and len(frame) > 1 else frame
            key = timeframe
            if frame is None or frame.empty:
                report["results"][asset][key] = {"error": "no market data"}
                continue
            variants = {}
            for target_rr in TARGET_VARIANTS:
                strategy = EmaAtrAdxTrend(target_rr=target_rr)
                result = run_backtest(
                    frame, strategy, asset, INITIAL_CAPITAL, RISK_PER_TRADE,
                    spread=spread, commission_per_lot=commission,
                    timeframe=timeframe,
                )
                wf = walk_forward(
                    frame, EmaAtrAdxTrend(target_rr=target_rr), asset,
                    initial_capital=INITIAL_CAPITAL, spread=spread,
                    commission_per_lot=commission,
                )
                variants[f"TP{1 if target_rr == 1.5 else 2}_{target_rr}R"] = {
                    "metrics": result.metrics,
                    "walk_forward": wf["summary"],
                }
            report["results"][asset][key] = {
                "bars": len(frame),
                "first": str(frame.index[0]),
                "last": str(frame.index[-1]),
                "fixed_spread": spread,
                "commission_per_lot_per_side": commission,
                "variants": variants,
            }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
