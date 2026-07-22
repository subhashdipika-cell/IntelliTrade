"""Background scheduler. Owns the recurring jobs:
  - trade monitor poll (every POLL_SECONDS) -> fires exit alerts on close.

Later: monthly model retrain + monthly journal analysis go here too."""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.logging_setup import get_logger
from app.workers.signal_scanner import signal_scanner
from app.workers.trade_monitor import trade_monitor

log = get_logger("workers.scheduler")

POLL_SECONDS = 15
SCAN_SECONDS = 60  # per-bar dedupe means this only acts on new closed bars
SNAPSHOT_DAYS = 7  # weekly backtest snapshot → Obsidian vault
RETRAIN_DAYS = 7   # weekly ML-filter retrain on fresh price history

_scheduler: BackgroundScheduler | None = None


def _weekly_snapshot() -> None:
    try:
        from app.services import vault_export
        res = vault_export.snapshot_backtests()
        log.info("Weekly backtest snapshot: %s", res.get("path") or res.get("error"))
    except Exception as exc:  # noqa: BLE001 — must not kill the scheduler
        log.warning("Weekly snapshot failed: %s", exc)


def _weekly_ml_retrain() -> None:
    """Retrain the per-asset ML meta-label filters on fresh H1 history — the
    same work as POST /ai/train, on a schedule so the models never go stale."""
    try:
        from app.ai_engine.model_trainer import train_asset
        from app.core.constants import SUPPORTED_ASSETS
        from app.services.mt5_client import mt5_client
        for asset in SUPPORTED_ASSETS:
            df = mt5_client.fetch_ohlcv(asset, "H1", 5000)
            res = train_asset(asset, df, horizon=5)
            log.info("Weekly ML retrain %s: %s", asset,
                     {k: res.get(k) for k in ("trained", "accuracy", "samples", "error")
                      if k in (res or {})})
    except Exception as exc:  # noqa: BLE001 — must not kill the scheduler
        log.warning("Weekly ML retrain failed: %s", exc)


def _keep_awake() -> None:
    """Hold the machine out of Modern Standby while the scanner runs.

    The 2026-07-21/22 outages: the on-battery sleep timer suspended the fleet
    repeatedly, so closed bars (and their one-bar cross events) went unseen.
    Same pattern as the AlphaEdge strategy-lab. ES_SYSTEM_REQUIRED keeps the
    system awake; the display may still sleep. Process-scoped — released when
    the backend exits.
    """
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    except Exception as exc:  # noqa: BLE001 — never block the scheduler
        log.warning("Keep-awake failed: %s", exc)


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _keep_awake,
        trigger="interval",
        seconds=60,  # re-assert every minute from the same worker thread pool
        id="keep_awake",
        max_instances=1,
        coalesce=True,
    )
    _keep_awake()
    _scheduler.add_job(
        trade_monitor.poll,
        trigger="interval",
        seconds=POLL_SECONDS,
        id="trade_monitor",
        max_instances=1,
        coalesce=True,  # if polls back up, run once, not a burst
    )
    _scheduler.add_job(
        signal_scanner.scan,
        trigger="interval",
        seconds=SCAN_SECONDS,
        id="signal_scanner",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        _weekly_snapshot,
        trigger="interval",
        days=SNAPSHOT_DAYS,
        id="weekly_snapshot",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        _weekly_ml_retrain,
        trigger="interval",
        days=RETRAIN_DAYS,
        id="weekly_ml_retrain",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    log.info("Scheduler started (monitor %ss, scanner %ss, snapshot %sd, retrain %sd).",
             POLL_SECONDS, SCAN_SECONDS, SNAPSHOT_DAYS, RETRAIN_DAYS)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("Scheduler stopped.")
