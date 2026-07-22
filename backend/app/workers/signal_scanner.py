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
    # How many closed bars BEFORE the newest one may be replayed after a scan
    # gap (standby/sleep). Small on purpose: older setups are stale setups.
    CATCHUP_BARS = 2

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
        from app.strategies.registry import strategy_scan_timeframe

        daily_loss = self._daily_loss_pct()

        # Per-asset strategy list when configured (backtest-driven selection),
        # else the global deployed list — see scanner_store.ScannerSettings.
        asset_strategies = (getattr(s, "strategies_by_asset", None) or {}).get(asset) or s.strategies

        # Bars are fetched per TIMEFRAME and cached — most strategies use the
        # global s.timeframe, but a strategy may declare its own (e.g. the M5
        # gold scalp), so we honour that without refetching for each strategy.
        df_cache: dict[str, object] = {}

        def bars(tf: str):
            if tf not in df_cache:
                d = mt5_client.fetch_ohlcv(asset, tf, 500)
                df_cache[tf] = d.iloc[:-1] if (d is not None and len(d) >= 3) else None
            return df_cache[tf]

        # Run every deployed strategy on this asset's latest closed bar (at the
        # strategy's own timeframe when it declares one).
        for strat in asset_strategies:
            tf = strategy_scan_timeframe(strat) or s.timeframe
            df = bars(tf)
            if df is None or len(df) < 3:
                continue
            bar_time = str(df.index[-1])
            key = f"{asset}:{tf}:{strat}"
            last_seen = self._last_bar.get(key)
            if last_seen == bar_time:
                continue  # this strategy already processed this bar
            self._last_bar[key] = bar_time

            # Missed-bar catch-up: bars that closed while the machine was in
            # standby were previously skipped outright (the scanner jumped
            # straight to the newest bar), so one-bar events like crossovers
            # were lost forever — the 2026-07-21/22 standby cycling produced
            # near-zero signals this way. Evaluate up to CATCHUP_BARS older
            # missed bars too, oldest first. Cold start (last_seen None)
            # keeps the old newest-bar-only behavior: replaying bars from
            # before a restart risks re-entering trades already taken.
            idxs = [len(df) - 1]
            if last_seen is not None:
                tail_start = max(len(df) - 1 - self.CATCHUP_BARS, 0)
                idxs = [i for i in range(tail_start, len(df))
                        if str(df.index[i]) > last_seen] or [len(df) - 1]

            for i in idxs:
                sub = df if i == len(df) - 1 else df.iloc[: i + 1]
                ctx = TradeContext(asset=asset, timeframe=tf, market_data=sub)
                pipeline = build_pipeline(
                    strategy_name=strat,
                    wiki_enabled=s.wiki_enabled,
                    daily_loss_pct=daily_loss,
                    include_execution=False,
                )
                ctx = pipeline.run(ctx)
                if ctx.blocked or ctx.signal is None:
                    continue

                # A signal from an older missed bar is only worth acting on
                # while price is still near it — beyond 0.75 ATR the move is
                # gone; chasing it would skew every SL/TP the signal carries.
                if i < len(df) - 1:
                    atr = self._atr14(df)
                    drift = abs(float(df["close"].iloc[-1]) - float(df["close"].iloc[i]))
                    if atr and drift > 0.75 * atr:
                        log.info("Catch-up signal stale [%s] bar=%s drift=%.2f ATR=%.2f — skipped.",
                                 key, df.index[i], drift, atr)
                        continue
                    log.info("Catch-up signal [%s]: missed bar %s recovered.", key, df.index[i])

                if s.mode == "autonomous":
                    self._maybe_execute(asset, ctx)
                else:
                    telegram.send_setup_alert(ctx.signal, ctx.capital_deployed, ctx.total_capital)
                    log.info("ALERT-ONLY setup [%s]: %s %s @ %s",
                             ctx.strategy, ctx.signal.direction.value, asset, ctx.signal.entry)
                break  # one action per strategy per scan — guardrails stay simple

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
    def _atr14(df) -> float:
        """ATR(14) of the last bar — drift guard for catch-up signals."""
        try:
            hl = df["high"] - df["low"]
            hc = (df["high"] - df["close"].shift()).abs()
            lc = (df["low"] - df["close"].shift()).abs()
            import pandas as pd
            tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
            return float(tr.rolling(14).mean().iloc[-1])
        except Exception:
            return 0.0

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
