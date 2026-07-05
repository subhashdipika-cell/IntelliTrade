"""Signal scanner — the autonomous side of the system.

Runs on a schedule. For each deployed asset it evaluates the latest CLOSED bar
through the pipeline (strategy → AI → Wiki → Risk, no execution stage). If a
setup passes:
  - alert_only  : send a 'setup found' Telegram alert (no order),
  - autonomous  : place the order via the execution stage (entry alert + monitor
                  then handle the rest), subject to guardrails.

Dedupe: each (asset, timeframe) is processed at most once per closed bar, so a
standing setup isn't traded repeatedly. The forming bar is dropped before
evaluation so signals fire on completed candles only."""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.logging_setup import get_logger
from app.pipeline.context import TradeContext
from app.pipeline.factory import build_pipeline
from app.pipeline.stages.execution import ExecutionStage
from app.services import telegram
from app.services.history_store import history_store
from app.services.mt5_client import mt5_client
from app.services.scanner_store import scanner_settings
from app.services.settings_store import money_settings
from app.services.trade_store import open_trades

log = get_logger("workers.scanner")


class SignalScanner:
    def __init__(self) -> None:
        self._last_bar: dict[str, str] = {}

    def status(self) -> dict:
        s = scanner_settings.get()
        return {"enabled": s.enabled, "mode": s.mode, "last_bars": dict(self._last_bar)}

    def scan(self) -> None:
        s = scanner_settings.get()
        if not s.enabled:
            return
        for asset in s.assets:
            try:
                self._scan_asset(asset, s)
            except Exception as exc:  # noqa: BLE001 — one asset must not kill the scan
                log.warning("Scan failed for %s: %s", asset, exc)

    def _scan_asset(self, asset: str, s) -> None:
        df = mt5_client.fetch_ohlcv(asset, s.timeframe, 500)
        if df is None or len(df) < 3:
            return
        df = df.iloc[:-1]  # drop the still-forming bar → evaluate the last CLOSED bar
        bar_time = str(df.index[-1])
        daily_loss = self._daily_loss_pct()

        # Run every deployed strategy on this asset's latest closed bar.
        for strat in s.strategies:
            key = f"{asset}:{s.timeframe}:{strat}"
            if self._last_bar.get(key) == bar_time:
                continue  # this strategy already processed this bar
            self._last_bar[key] = bar_time

            ctx = TradeContext(asset=asset, timeframe=s.timeframe, market_data=df)
            pipeline = build_pipeline(
                strategy_name=strat,
                wiki_enabled=s.wiki_enabled,
                daily_loss_pct=daily_loss,
                include_execution=False,
            )
            ctx = pipeline.run(ctx)
            if ctx.blocked or ctx.signal is None:
                continue

            if s.mode == "autonomous":
                self._maybe_execute(asset, ctx)
            else:
                telegram.send_setup_alert(ctx.signal, ctx.capital_deployed, ctx.total_capital)
                log.info("ALERT-ONLY setup [%s]: %s %s @ %s",
                         ctx.strategy, ctx.signal.direction.value, asset, ctx.signal.entry)

    def _maybe_execute(self, asset: str, ctx: TradeContext) -> None:
        # Guardrail: one open position per asset.
        if self._has_open_position(asset):
            log.info("Skip %s: position already open.", asset)
            return
        # Guardrail: max concurrent open trades.
        max_open = money_settings.get().max_open_trades
        if len(open_trades) >= max_open:
            log.info("Skip %s: max open trades (%d) reached.", asset, max_open)
            return
        ExecutionStage().process(ctx)  # places order, entry alert, registers w/ monitor

    @staticmethod
    def _has_open_position(asset: str) -> bool:
        for ticket in open_trades.tickets():
            c = open_trades.get(ticket)
            if c is not None and c.asset == asset:
                return True
        return False

    @staticmethod
    def _daily_loss_pct() -> float:
        """Today's realised loss as a positive %, from closed-trade history — feeds
        the Risk stage's daily hard-stop in autonomous mode."""
        today = datetime.now(timezone.utc).date().isoformat()
        rows = [r for r in history_store.all() if (r.get("closed_at") or "").startswith(today)]
        if not rows:
            return 0.0
        pnl = sum(r.get("pnl", 0.0) for r in rows)
        acct = mt5_client.account_info()
        balance = acct["balance"] if acct else None
        if not balance:
            return 0.0
        return max(0.0, -pnl / balance * 100)


signal_scanner = SignalScanner()
