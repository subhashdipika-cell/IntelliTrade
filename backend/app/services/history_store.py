"""Append-only store of closed trades + their decision trees.

Each closed trade is one JSON line in trade_history.jsonl. Append-only is robust
(a crash mid-write loses at most the last line) and trivial to read back. When you
add a real DB, swap the read/append internals — the interface stays the same.

This is what makes the loop persistent: signal → execute → monitor → STORE here →
review on the History page → monthly analysis."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from threading import Lock

from app.core.logging_setup import get_logger
from app.pipeline.context import TradeContext

log = get_logger("services.history")

_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
_HISTORY_PATH = os.path.join(_DATA_DIR, "trade_history.jsonl")


class HistoryStore:
    def __init__(self) -> None:
        self._lock = Lock()

    def append(self, record: dict) -> None:
        with self._lock:
            os.makedirs(_DATA_DIR, exist_ok=True)
            with open(_HISTORY_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        log.info("Stored closed trade %s (%s).", record.get("ticket"), record.get("outcome"))

    def all(self) -> list[dict]:
        if not os.path.exists(_HISTORY_PATH):
            return []
        records: list[dict] = []
        with self._lock, open(_HISTORY_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def recorded_tickets(self) -> set[int]:
        return {r["ticket"] for r in self.all() if r.get("ticket") is not None}

    def has_ticket(self, ticket: int | None) -> bool:
        return ticket is not None and ticket in self.recorded_tickets()


def build_record(ctx: TradeContext, pnl: float, close_price: float) -> dict:
    """Construct a history record from a closed TradeContext."""
    sig = ctx.signal
    decisions = ctx.explain()
    return {
        "ticket": ctx.ticket,
        "asset": ctx.asset,
        "strategy": ctx.strategy,
        "direction": sig.direction.value if sig else None,
        "entry": sig.entry if sig else None,
        "sl": sig.stop_loss if sig else None,
        "tp": sig.target if sig else None,
        "lots": sig.lots if sig else None,
        "close_price": round(close_price, 5),
        "outcome": ctx.outcome.value,
        "pnl": round(pnl, 2),
        "capital_deployed": ctx.capital_deployed,
        "total_capital_before": ctx.total_capital,
        "final_capital": ctx.final_capital,
        "opened_at": decisions[0]["at"] if decisions else None,
        "closed_at": datetime.now(timezone.utc).isoformat(),
        "decision_tree": decisions,
    }


history_store = HistoryStore()
