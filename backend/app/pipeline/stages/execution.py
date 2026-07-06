"""Execution stage — places the order, then fires the Telegram ENTRY alert.

Live-money guard: refuses to place a real order unless ALLOW_LIVE is true AND the
terminal's reported account type matches what config expects. The entry alert is
sent ONLY after the broker confirms the order, so you never get an alert for a
trade that didn't actually open."""
from __future__ import annotations

from app.core.config import settings
from app.pipeline.base import Stage
from app.pipeline.context import Decision, TradeContext, Verdict
from app.services import telegram
from app.services.mt5_client import mt5_client
from app.services.trade_store import open_trades


class ExecutionStage(Stage):
    name = "execution"

    def process(self, ctx: TradeContext) -> TradeContext:
        if ctx.signal is None:
            ctx.record(Decision(self.name, Verdict.SKIP, "No signal to execute."))
            return ctx

        guard = self._live_guard()
        if guard is not None:
            ctx.record(Decision(self.name, Verdict.BLOCK, guard))
            return ctx

        sig = ctx.signal
        result = mt5_client.place_order(
            asset=sig.asset, direction=sig.direction.value,
            lots=sig.lots, sl=sig.stop_loss, tp=sig.target,
            strategy=ctx.strategy,   # stamped into the MT5 comment for attribution
        )
        if not result.get("ok"):
            ctx.record(Decision(self.name, Verdict.BLOCK,
                                f"Order rejected: {result.get('reason')}"))
            return ctx

        ctx.ticket = result.get("ticket")
        ctx.record(Decision(self.name, Verdict.PASS,
                            f"Order placed (ticket={ctx.ticket})."))

        # Hand the open trade to the monitor worker so it can fire the exit alert.
        if ctx.ticket is not None:
            open_trades.register(ctx.ticket, ctx)

        # ── Telegram ENTRY alert ──────────────────────────────────────────────
        # asset, entry, SL, target, capital deployed, total capital
        telegram.alert_from_context_entry(ctx)
        return ctx

    def _live_guard(self) -> str | None:
        """Returns a block reason if it is unsafe to trade, else None."""
        from app.services.account_state import account_state

        expected = account_state.active()
        actual = mt5_client.verify_account_type()  # None in stub mode

        if expected == "LIVE":
            if not settings.allow_live:
                return "LIVE blocked: ALLOW_LIVE is false (real-money kill switch)."
            if actual is not None and actual != "LIVE":
                return f"LIVE mismatch: terminal reports '{actual}', refusing to trade."
        elif expected == "DEMO":
            if actual is not None and actual == "LIVE":
                return "Config says DEMO but terminal is LIVE — refusing to trade."
        return None
