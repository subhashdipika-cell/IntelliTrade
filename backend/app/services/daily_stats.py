"""Today's realised P&L tally — feeds the daily-loss stop and the profit lock.

Reads closed trades from the history store (same source the scanner's daily-loss
guard uses), ordered by close time, and tracks the intraday PEAK of the running
total — the peak is what the give-back lock protects.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.services.history_store import history_store
from app.services.mt5_client import mt5_client


def daily_realized_stats() -> dict:
    today = datetime.now(timezone.utc).date().isoformat()
    rows = [r for r in history_store.all() if (r.get("closed_at") or "").startswith(today)]
    rows.sort(key=lambda r: r.get("closed_at") or "")
    cum = peak = 0.0
    for r in rows:
        cum += float(r.get("pnl") or 0.0)
        peak = max(peak, cum)
    acct = mt5_client.account_info()
    balance = (acct or {}).get("balance") or None
    return {"pnl": round(cum, 2), "peak": round(peak, 2), "trades": len(rows), "balance": balance}
