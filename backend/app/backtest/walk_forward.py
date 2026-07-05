"""Walk-forward / out-of-sample validation.

A single backtest overfits and will lie to you. This splits the data into rolling
(in-sample → out-of-sample) folds and reports OOS performance per fold. Only the
out-of-sample numbers are trustworthy for deciding whether to deploy."""
from __future__ import annotations

import pandas as pd

from app.backtest.engine import run_backtest
from app.strategies.base import Strategy


def walk_forward(df: pd.DataFrame, strategy: Strategy, asset: str = "GOLD",
                 n_folds: int = 5, oos_fraction: float = 0.3,
                 initial_capital: float = 1000.0, spread: float = 0.0,
                 commission_pct: float = 0.0, commission_per_trade: float = 0.0,
                 commission_per_lot: float = 0.0) -> dict:
    """Rolling folds. Here the strategy is assumed pre-parameterized; the IS
    segment is the place to plug optimization later (grid / Bayesian) before
    scoring on the untouched OOS segment."""
    fold_size = len(df) // n_folds
    folds: list[dict] = []

    for k in range(n_folds):
        start = k * fold_size
        end = start + fold_size if k < n_folds - 1 else len(df)
        segment = df.iloc[start:end]
        if len(segment) < 50:
            continue
        split = int(len(segment) * (1 - oos_fraction))
        oos = segment.iloc[split:]

        # TODO: optimize params on segment.iloc[:split] (in-sample) here.
        oos_result = run_backtest(
            oos, strategy, asset, initial_capital, spread=spread,
            commission_pct=commission_pct, commission_per_trade=commission_per_trade,
            commission_per_lot=commission_per_lot,
        )
        folds.append({
            "fold": k + 1,
            "oos_bars": len(oos),
            "oos_metrics": oos_result.metrics,
        })

    oos_returns = [f["oos_metrics"]["total_return_pct"] for f in folds]
    return {
        "folds": folds,
        "summary": {
            "mean_oos_return_pct": round(sum(oos_returns) / len(oos_returns), 2)
            if oos_returns else 0.0,
            "positive_folds": sum(1 for r in oos_returns if r > 0),
            "total_folds": len(folds),
            # robustness signal: consistency across folds matters more than peak return
            "consistency": round(
                sum(1 for r in oos_returns if r > 0) / len(oos_returns), 2
            ) if oos_returns else 0.0,
        },
    }
