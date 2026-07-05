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

_scheduler: BackgroundScheduler | None = None


def _weekly_snapshot() -> None:
    try:
        from app.services import vault_export
        res = vault_export.snapshot_backtests()
        log.info("Weekly backtest snapshot: %s", res.get("path") or res.get("error"))
    except Exception as exc:  # noqa: BLE001 — must not kill the scheduler
        log.warning("Weekly snapshot failed: %s", exc)


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(daemon=True)
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
    _scheduler.start()
    log.info("Scheduler started (monitor %ss, scanner %ss, snapshot %sd).",
             POLL_SECONDS, SCAN_SECONDS, SNAPSHOT_DAYS)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("Scheduler stopped.")
