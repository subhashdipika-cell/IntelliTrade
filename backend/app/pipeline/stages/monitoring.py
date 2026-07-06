"""Trade monitoring — runs on a schedule (NOT inline with signal birth).

Polls open MT5 positions, detects closes, classifies the outcome
(TGT / SL / TSL / MANUAL), persists it, and fires the Telegram EXIT alert.

`on_trade_closed()` is the single entry point the monitor worker calls per
detected close."""
from __future__ import annotations

from app.core.logging_setup import get_logger
from app.pipeline.context import Outcome, TradeContext
from app.services import telegram
from app.services.history_store import build_record, history_store
from app.services.mt5_client import mt5_client

log = get_logger("pipeline.monitoring")


def classify_outcome(reason: str, direction: str | None = None,
                     close_price: float | None = None,
                     signal_sl: float | None = None) -> Outcome:
    """Classify from the MT5 deal reason (authoritative), not price guessing.
      TP → TGT,  SL/SO → SL,  else → MANUAL.
    A stop that was actually trailed (the trailing manager moved it, so the close
    lands notably better than the ORIGINAL SL) is reported as TSL."""
    if reason == "TP":
        return Outcome.TGT
    if reason in ("SL", "SO"):
        if direction and close_price is not None and signal_sl:
            tol = max(abs(signal_sl) * 0.0008, 1e-9)
            if direction == "BUY" and close_price > signal_sl + tol:
                return Outcome.TSL
            if direction == "SELL" and close_price < signal_sl - tol:
                return Outcome.TSL
        return Outcome.SL
    return Outcome.MANUAL


def on_trade_closed(ctx: TradeContext, close_price: float, pnl: float,
                    reason: str = "MANUAL") -> TradeContext:
    """Called by the monitor worker when a tracked position is detected closed."""
    sig = ctx.signal
    ctx.outcome = (
        classify_outcome(reason, sig.direction.value, close_price, sig.stop_loss)
        if sig is not None else classify_outcome(reason)
    )

    acct = mt5_client.account_info()
    ctx.final_capital = acct["equity"] if acct else (
        (ctx.total_capital or 0.0) + pnl
    )

    log.info("Trade %s closed: %s (reason=%s), pnl=%.2f, capital=%.2f",
             ctx.ticket, ctx.outcome.value, reason, pnl, ctx.final_capital or 0.0)

    # Persist (dedup by ticket so reconcile + live path never double-record).
    record = build_record(ctx, pnl=pnl, close_price=close_price)
    if not history_store.has_ticket(ctx.ticket):
        history_store.append(record)

    # ── Telegram EXIT alert ───────────────────────────────────────────────────
    telegram.alert_from_context_exit(ctx, pnl=pnl)

    # ── Auto-log to the Obsidian vault (regime-tagged) — fail-soft ────────────
    try:
        from app.services import vault_export
        from app.services.account_state import account_state
        vault_export.export_trade(record, df=ctx.market_data, account=account_state.active())
    except Exception as exc:  # noqa: BLE001 — never break monitoring on a vault error
        log.warning("Vault export failed for ticket %s: %s", ctx.ticket, exc)
    return ctx


def reattach_open_trades() -> int:
    """Rebuild a TradeContext for each currently-open IntelliTrade position and
    register it with the monitor. Without this, a trade left open across a backend
    restart loses its in-memory tracking, so its close fires NO exit alert and
    isn't trailed (it only gets silently backfilled into History by reconcile).
    The position's live SL/TP are used as the signal bracket. Returns count added."""
    from app.core.constants import SYMBOL_MAPPER
    from app.pipeline.context import Decision, Direction, Signal, TradeContext, Verdict
    from app.services.mt5_client import _MAGIC, mt5_client
    from app.services.trade_store import open_trades

    rev = {v: k for k, v in SYMBOL_MAPPER.items()}
    acct = mt5_client.account_info()
    equity = acct["equity"] if acct else None
    tracked = open_trades.tickets()

    added = 0
    for p in mt5_client.open_positions_by_magic(_MAGIC):
        if p["ticket"] in tracked:
            continue
        asset = rev.get(p["symbol"], p["symbol"])
        ctx = TradeContext(asset=asset, timeframe="H1")
        ctx.signal = Signal(asset, Direction(p["direction"]), p["entry"],
                            p["sl"], p["tp"], "H1", p["lots"])
        ctx.ticket = p["ticket"]
        ctx.total_capital = equity
        # Recover the strategy from the MT5 order comment ("IT <name>") so a
        # restart no longer erases attribution in History.
        ctx.strategy = p.get("strategy")
        ctx.record(Decision("reattach", Verdict.INFO,
                            "Re-attached open position to monitor after restart.",
                            at=p["opened_at"]))
        open_trades.register(p["ticket"], ctx)
        added += 1
    return added


def reconcile_from_mt5(days: int = 7) -> int:
    """Backfill the History store from MT5 deal history (source of truth) for any
    closed IntelliTrade trades not already recorded — e.g. trades that closed
    while the backend was down, or were open across a restart. Returns the count
    added."""
    from app.core.constants import SYMBOL_MAPPER
    from app.services.mt5_client import _MAGIC, mt5_client
    from app.services.trade_store import open_trades

    existing = history_store.recorded_tickets()
    pending = open_trades.tickets()  # let the live path handle still-tracked trades
    rev = {v: k for k, v in SYMBOL_MAPPER.items()}

    added = 0
    for t in mt5_client.closed_trades_by_magic(_MAGIC, days=days):
        pid = t["position_id"]
        if pid in existing or pid in pending:
            continue
        record = {
            "ticket": pid,
            "asset": rev.get(t["symbol"], t["symbol"]),
            "strategy": t.get("strategy"),         # from the "IT <name>" MT5 comment (None for pre-stamping trades)
            "direction": t["direction"],
            "entry": t["entry_price"],
            "sl": None,
            "tp": None,
            "lots": t["lots"],
            "close_price": round(t["close_price"], 5),
            "outcome": classify_outcome(t["reason"]).value,
            "pnl": t["pnl"],
            "capital_deployed": None,
            "total_capital_before": None,
            "final_capital": None,
            "opened_at": t["opened_at"],
            "closed_at": t["closed_at"],
            "decision_tree": [],
            "source": "mt5_reconcile",
        }
        history_store.append(record)
        added += 1

        # Safety-net alert: if this trade closed RECENTLY (e.g. while the backend
        # was briefly down) fire the exit alert here, since the live path missed
        # it. Gated by recency so a first-run backfill of old trades never spams.
        try:
            from datetime import datetime, timedelta, timezone
            closed = datetime.fromisoformat(t["closed_at"])
            if datetime.now(timezone.utc) - closed < timedelta(hours=3):
                from app.pipeline.context import Outcome
                from app.services import telegram
                acct = mt5_client.account_info()
                telegram.send_exit_alert(
                    record["asset"], Outcome(record["outcome"]),
                    acct["equity"] if acct else 0.0, pnl=t["pnl"],
                )
        except Exception as exc:  # noqa: BLE001 — alert must never break reconcile
            log.warning("Reconcile alert failed for %s: %s", pid, exc)
    return added
