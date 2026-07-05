"""Trade monitor — polls MT5 for closed positions and fires the exit alert.

Runs on a schedule (see scheduler.py), NOT inline with signal birth. Each poll:
  1. ask MT5 for currently-open tickets,
  2. diff against the tickets we registered at execution time,
  3. for any that vanished, pull the closing deal (price + realised P/L),
  4. hand it to monitoring.on_trade_closed() which classifies TGT/SL/TSL,
     persists, and sends the Telegram exit alert.

A close that can't be resolved yet (deal history not posted) is left in the
store and retried on the next poll — we never drop a trade silently."""
from __future__ import annotations

from app.core.logging_setup import get_logger
from app.pipeline.stages.monitoring import on_trade_closed, reconcile_from_mt5
from app.services import gold_hours, trailing
from app.services.mt5_client import mt5_client
from app.services.trade_store import open_trades

log = get_logger("workers.monitor")


class TradeMonitor:
    def poll(self) -> None:
        # 0. Friday gold cutoff: flatten open GOLD positions before Vantage's
        #    (possibly early, US-holiday) Friday close — see services/gold_hours.
        #    The close is picked up by the normal tracked-diff below, so the
        #    exit alert + history entry still fire.
        try:
            _, flatten = gold_hours.friday_state()
            if flatten:
                for ticket in mt5_client.open_gold_tickets():
                    res = mt5_client.close_position(ticket)
                    log.info("Friday gold cutoff: closing #%s -> %s", ticket, res.get("reason"))
        except Exception as exc:  # noqa: BLE001 — cutoff must not kill the poll
            log.warning("Friday gold flatten failed: %s", exc)
        # 1. Live, tracked trades → trail open ones, then classify closed ones
        #    (decision tree + Telegram exit alert).
        self._process_tracked()
        # 2. Safety net: reconcile from MT5 deal history so trades that closed
        #    while the backend was down (or open across a restart) are never lost.
        try:
            added = reconcile_from_mt5(days=7)
            if added:
                log.info("Reconciled %d closed trade(s) from MT5 history.", added)
        except Exception as exc:  # noqa: BLE001
            log.warning("History reconcile failed: %s", exc)

    def _process_tracked(self) -> None:
        tracked = open_trades.tickets()
        if not tracked:
            return
        try:
            live_tickets = mt5_client.open_position_tickets()
        except Exception as exc:  # noqa: BLE001 — a poll error must not kill the scheduler
            log.warning("Monitor poll failed to read positions: %s", exc)
            return

        # Still-open tracked trades → advance the trailing stop.
        for ticket in tracked & live_tickets:
            ctx = open_trades.get(ticket)
            if ctx is None:
                continue
            try:
                trailing.update_trade(ctx)
            except Exception as exc:  # noqa: BLE001 — trailing must not kill the poll
                log.warning("Trailing update failed for ticket %s: %s", ticket, exc)

        # Vanished tracked trades → resolve the close and fire the exit alert.
        for ticket in tracked - live_tickets:
            ctx = open_trades.get(ticket)
            if ctx is None:
                open_trades.remove(ticket)
                continue
            result = mt5_client.fetch_close_result(ticket)
            if result is None:
                log.info("Ticket %s closed but deal not posted yet; retrying.", ticket)
                continue
            try:
                on_trade_closed(
                    ctx,
                    close_price=result["price"],
                    pnl=result["pnl"],
                    reason=result.get("reason", "MANUAL"),
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("on_trade_closed failed for ticket %s: %s", ticket, exc)
            finally:
                open_trades.remove(ticket)


trade_monitor = TradeMonitor()
