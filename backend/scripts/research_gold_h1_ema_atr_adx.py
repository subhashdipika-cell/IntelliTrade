"""Bounded Gold H1 specialization search using completed MT5 DEMO bars."""
from __future__ import annotations

from itertools import product
import json

import MetaTrader5 as mt5

from app.backtest.engine import run_backtest
from app.backtest.walk_forward import walk_forward
from app.core.constants import default_commission_per_lot, to_terminal_symbol
from app.services.mt5_client import mt5_client
from app.strategies.gold_h1_ema_atr_adx import GoldH1EmaAtrAdx


def main() -> None:
    if not mt5_client.connect() or mt5_client.verify_account_type() != "DEMO":
        raise SystemExit("Verified MT5 DEMO connection required")
    frame = mt5_client.fetch_ohlcv("GOLD", "H1", 10_000)
    frame = frame.iloc[:-1]
    info = mt5.symbol_info(to_terminal_symbol("GOLD"))
    spread = float(info.spread * info.point) if info is not None else 0.0
    commission = default_commission_per_lot("GOLD")

    rows: list[dict] = []
    combinations = product(
        ((7, 18), (12, 18)),
        (100, 200),
        (18.0, 20.0),
        (10.0, 20.0),
        (2.0, 2.5),
    )
    for session, long_ema, adx, min_atr, target_rr in combinations:
        params = {
            "session_start_utc": session[0],
            "session_end_utc": session[1],
            "long_ema_length": long_ema,
            "adx_threshold": adx,
            "min_atr_percentile": min_atr,
            "max_atr_percentile": 95.0,
            "target_rr": target_rr,
        }
        strategy = GoldH1EmaAtrAdx(**params)
        result = run_backtest(
            frame, strategy, "GOLD", 1000.0, 0.01,
            spread=spread, commission_per_lot=commission, timeframe="H1",
        )
        wf = walk_forward(
            frame, GoldH1EmaAtrAdx(**params), "GOLD",
            initial_capital=1000.0, spread=spread,
            commission_per_lot=commission,
        )
        fold_metrics = [fold["oos_metrics"] for fold in wf["folds"]]
        metrics = result.metrics
        rows.append({
            "parameters": params,
            "metrics": metrics,
            "walk_forward": {
                **wf["summary"],
                "folds_pf_ge_1": sum(
                    1 for m in fold_metrics
                    if m["profit_factor"] is not None and m["profit_factor"] >= 1.0
                ),
                "folds_pf_ge_1_2": sum(
                    1 for m in fold_metrics
                    if m["profit_factor"] is not None and m["profit_factor"] >= 1.2
                ),
            },
            "demo_research_gate": bool(
                metrics["total_trades"] >= 100
                and metrics["profit_factor"] is not None
                and metrics["profit_factor"] >= 1.10
                and metrics["total_return_pct"] > 0
                and abs(metrics["max_drawdown_pct"]) <= 20
                and wf["summary"]["positive_folds"] >= 3
                and wf["summary"]["mean_oos_return_pct"] > 0
            ),
        })

    rows.sort(key=lambda row: (
        row["demo_research_gate"],
        row["walk_forward"]["positive_folds"],
        row["walk_forward"]["mean_oos_return_pct"],
        row["walk_forward"]["folds_pf_ge_1"],
        row["metrics"]["profit_factor"] or 0.0,
        row["metrics"]["total_return_pct"],
    ), reverse=True)
    print(json.dumps({
        "scope": "HISTORICAL_RESEARCH_ONLY",
        "bars": len(frame),
        "first": str(frame.index[0]),
        "last": str(frame.index[-1]),
        "fixed_spread": spread,
        "commission_per_lot_per_side": commission,
        "candidates_tested": len(rows),
        "selected": rows[0],
        "top_10": rows[:10],
    }, indent=2))


if __name__ == "__main__":
    main()
