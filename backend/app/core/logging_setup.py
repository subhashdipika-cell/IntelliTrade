"""Minimal structured logging for the pipeline and services."""
import logging
import sys

_FORMAT = "[%(asctime)s] %(levelname)-7s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: int = logging.INFO) -> None:
    # Force UTF-8 so non-ASCII in log messages (e.g. the "→" in trail/decision
    # logs) never crashes the handler on a cp1252 Windows console/file stream.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — older/odd streams: fall through
        pass
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers[:] = [handler]

    # httpx logs the full request URL — which for Telegram contains the bot token.
    # Quiet it so secrets never hit the logs. Also trim APScheduler's per-poll noise.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
