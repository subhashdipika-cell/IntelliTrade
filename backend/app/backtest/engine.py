"""Event-driven backtester.

Walks bar by bar (no vectorized lookahead), opens a position when the strategy
fires on a closed bar, and exits on SL/TP touch.

Costs modelled so net profitability is honest. They stack — use whichever
matches your broker:
  - spread          : price slippage applied to the entry fill (price units).
  - commission_per_lot : broker commission per STANDARD LOT per SIDE (entry AND
                      exit). This is the Vantage-accurate model — position size
                      is converted to lots via the asset's contract size.
  - commission_pct  : commission as % of notional, charged PER SIDE.
  - commission_per_trade : flat fee per round-turn trade (account currency).

Every trade record carries lots, gross_pnl, commission and net pnl, and the
metrics report total commission paid plus gross-vs-net return so the drag is
visible."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.core.constants import units_to_lots
from app.pipeline.context import Direction
from app.strategies.base import Strategy


@dataclass
class BacktestResult:
    metrics: dict
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)


def run_backtest(df: pd.DataFrame, strategy: Strategy, asset: str = "GOLD",
                 initial_capital: float = 1000.0, risk_per_trade: float = 0.01,
                 spread: float = 0.0, commission_pct: float = 0.0,
                 commission_per_trade: float = 0.0, commission_per_lot: float = 0.0,
                 timeframe: str = "H1") -> BacktestResult:
    equity = initial_capital
    curve: list[float] = []
    trades: list[dict] = []
    position: dict | None = None

    # Indicators are computed ONCE here (vectorised), not re-derived per bar — this
    # is what makes the backtest O(n) instead of O(n^2). signals[i] is the setup on
    # bar i, identical to the old per-bar generate(df[:i+1]) because rolling/ewm are
    # causal.
    signals = strategy.signals(asset, df, timeframe)

    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    times = df.index

    for i in range(2, len(df)):
        high, low = highs[i], lows[i]

        # manage open position against this bar's range
        if position is not None:
            hit = _check_exit(position, high, low)
            if hit is not None:
                exit_price, reason = hit
                gross = _pnl(position, exit_price)
                commission = _commission(position, exit_price, commission_pct,
                                         commission_per_trade, commission_per_lot)
                net = gross - commission
                equity += net
                trades.append({
                    **position, "exit": exit_price, "reason": reason,
                    "gross_pnl": round(gross, 2),
                    "commission": round(commission, 2),
                    "pnl": round(net, 2),
                    "equity": round(equity, 2),
                })
                position = None

        # look for a new entry only when flat
        if position is None:
            sig = signals[i]
            if sig is not None:
                entry = sig.entry + (spread if sig.direction is Direction.BUY else -spread)
                size = (equity * risk_per_trade) / max(abs(entry - sig.stop_loss), 1e-9)
                position = {
                    "direction": sig.direction.value, "entry": round(entry, 5),
                    "sl": sig.stop_loss, "tp": sig.target, "size": round(size, 4),
                    "lots": round(units_to_lots(asset, size), 4),
                    "time": str(times[i]),
                }
        curve.append(round(equity, 2))

    return BacktestResult(
        _metrics(initial_capital, equity, trades, curve), trades, curve
    )


def _check_exit(pos: dict, high: float, low: float):
    if pos["direction"] == "BUY":
        if low <= pos["sl"]:
            return pos["sl"], "SL"
        if high >= pos["tp"]:
            return pos["tp"], "TGT"
    else:
        if high >= pos["sl"]:
            return pos["sl"], "SL"
        if low <= pos["tp"]:
            return pos["tp"], "TGT"
    return None


def _pnl(pos: dict, exit_price: float) -> float:
    diff = exit_price - pos["entry"]
    if pos["direction"] == "SELL":
        diff = -diff
    return diff * pos["size"]


def _commission(pos: dict, exit_price: float, commission_pct: float,
                commission_per_trade: float, commission_per_lot: float) -> float:
    """Round-turn brokerage, stacking whichever models are set:
      - per-lot: lots * rate, charged on entry AND exit (x2),
      - pct of notional on entry AND exit,
      - flat fee per round-turn trade."""
    per_lot_cost = pos.get("lots", 0.0) * commission_per_lot * 2  # entry + exit sides
    notional = (pos["entry"] + exit_price) * pos["size"]          # both sides
    pct_cost = notional * (commission_pct / 100.0)
    return per_lot_cost + pct_cost + commission_per_trade


def _metrics(initial: float, final: float, trades: list[dict], curve: list[float]) -> dict:
    n = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    total_commission = sum(t.get("commission", 0.0) for t in trades)
    total_lots = sum(t.get("lots", 0.0) for t in trades)
    gross_profit = sum(t.get("gross_pnl", t["pnl"]) for t in trades)
    net_profit = final - initial

    arr = np.array(curve) if curve else np.array([initial])
    peak = np.maximum.accumulate(arr)
    max_dd = float(((arr - peak) / peak).min() * 100) if len(arr) else 0.0
    rets = np.diff(arr) / arr[:-1] if len(arr) > 1 else np.array([0.0])
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252 * 24)) if rets.std() else 0.0

    return {
        "total_return_pct": round((final / initial - 1) * 100, 2),
        "gross_return_pct": round(gross_profit / initial * 100, 2),
        "final_balance": round(final, 2),
        "net_profit": round(net_profit, 2),
        "gross_profit": round(gross_profit, 2),
        "total_commission": round(total_commission, 2),
        "commission_drag_pct": round(total_commission / initial * 100, 2),
        "total_lots_traded": round(total_lots, 2),
        "total_trades": n,
        "win_rate_pct": round(len(wins) / n * 100, 2) if n else 0.0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
        "avg_win": round(gross_win / len(wins), 2) if wins else 0.0,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0.0,
        "avg_commission_per_trade": round(total_commission / n, 2) if n else 0.0,
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe": round(sharpe, 2),
    }
