"""Registry of currently-open trades, keyed by MT5 ticket.

The execution stage registers a TradeContext here the moment an order is
confirmed; the monitor worker reads it back when the position closes so it can
classify the outcome and fire the exit alert with the original SL/TP/capital.

In-memory for the MVP (the app is a single laptop process). When you add a DB,
back this with a table so open trades survive a restart — the interface stays
the same."""
from __future__ import annotations

from threading import Lock

from app.pipeline.context import TradeContext


class OpenTradeStore:
    def __init__(self) -> None:
        self._trades: dict[int, TradeContext] = {}
        self._lock = Lock()

    def register(self, ticket: int, ctx: TradeContext) -> None:
        with self._lock:
            self._trades[ticket] = ctx

    def get(self, ticket: int) -> TradeContext | None:
        with self._lock:
            return self._trades.get(ticket)

    def remove(self, ticket: int) -> TradeContext | None:
        with self._lock:
            return self._trades.pop(ticket, None)

    def tickets(self) -> set[int]:
        with self._lock:
            return set(self._trades.keys())

    def __len__(self) -> int:
        with self._lock:
            return len(self._trades)


open_trades = OpenTradeStore()
