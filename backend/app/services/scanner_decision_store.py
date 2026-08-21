"""Bounded, persistent audit journal for completed-candle scanner decisions."""
from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timedelta, timezone
import json
import os
from threading import Lock
from typing import Any

from app.core.logging_setup import get_logger
from app.pipeline.context import TradeContext

_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
_PATH = os.path.join(_DATA_DIR, "scanner_decisions.jsonl")
log = get_logger("services.scanner_decisions")


class ScannerDecisionStore:
    def __init__(self, path: str = _PATH, max_records: int = 20_000) -> None:
        self.path = path
        self.max_records = max_records
        self._lock = Lock()
        self._rows: deque[dict[str, Any]] = deque(maxlen=max_records)
        self._writes = 0
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    try:
                        self._rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return

    def record(self, ctx: TradeContext, *, bar_time: str, mode: str,
               status: str | None = None, blocker: str | None = None,
               reason: str | None = None, catchup: bool = False) -> dict[str, Any]:
        blocked_decision = next(
            (d for d in reversed(ctx.decisions) if d.verdict.value == "BLOCK"), None
        )
        ai_decision = next(
            (d for d in reversed(ctx.decisions)
             if d.stage == "ai_filter" and d.score is not None), None
        )
        if status is None:
            status = "blocked" if ctx.blocked or ctx.signal is None else "passed"
        if blocker is None and status == "blocked":
            blocker = ctx.blocked_by or (blocked_decision.stage if blocked_decision else "scanner")
        if reason is None:
            reason = blocked_decision.reason if blocked_decision else (
                ctx.decisions[-1].reason if ctx.decisions else "No decision recorded"
            )
        signal = None
        if ctx.signal is not None:
            signal = {
                "direction": ctx.signal.direction.value,
                "entry": ctx.signal.entry,
                "sl": ctx.signal.stop_loss,
                "tp": ctx.signal.target,
                "lots": ctx.signal.lots,
            }
        row = {
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "bar_time": bar_time,
            "asset": ctx.asset,
            "timeframe": ctx.timeframe,
            "strategy": ctx.strategy,
            "mode": mode,
            "status": status,
            "blocked_by": blocker,
            "reason": reason,
            "catchup": catchup,
            "ai_score": ai_decision.score if ai_decision else None,
            "signal": signal,
            "ticket": ctx.ticket,
            "decision_tree": ctx.explain(),
        }
        self.append(row)
        return row

    def append(self, row: dict[str, Any]) -> None:
        with self._lock:
            self._rows.append(row)
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, separators=(",", ":")) + "\n")
                self._writes += 1
                if len(self._rows) == self.max_records and self._writes % 500 == 0:
                    self._rewrite()
            except OSError as exc:
                # Diagnostics must never stop the autonomous scanner.
                log.warning("Could not persist scanner decision: %s", exc)

    def _rewrite(self) -> None:
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for row in self._rows:
                f.write(json.dumps(row, separators=(",", ":")) + "\n")
        os.replace(tmp, self.path)

    def recent(self, limit: int = 100, *, asset: str | None = None,
               strategy: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(reversed(self._rows))
        if asset:
            rows = [r for r in rows if str(r.get("asset", "")).upper() == asset.upper()]
        if strategy:
            needle = strategy.strip().lower()
            rows = [r for r in rows if needle in str(r.get("strategy", "")).lower()]
        if status:
            rows = [r for r in rows if r.get("status") == status]
        return rows[:max(1, min(limit, 1000))]

    def blocker_summary(self, hours: int = 24) -> dict[str, Any]:
        bounded_hours = max(1, min(hours, 24 * 90))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=bounded_hours)
        with self._lock:
            rows = [r for r in self._rows if _timestamp(r.get("evaluated_at")) >= cutoff]
        blocked = [r for r in rows if r.get("status") == "blocked"]
        return {
            "hours": bounded_hours,
            "evaluations": len(rows),
            "blocked": len(blocked),
            "passed": len(rows) - len(blocked),
            "by_stage": dict(Counter(r.get("blocked_by") or "unknown" for r in blocked)),
            "by_strategy": dict(Counter(r.get("strategy") or "unknown" for r in blocked)),
            "by_reason": dict(Counter(_reason_group(r.get("reason")) for r in blocked)),
            "latest": list(reversed(blocked[-20:])),
        }


def _timestamp(value: Any) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _reason_group(value: Any) -> str:
    reason = str(value or "unknown")
    lowered = reason.lower()
    if reason.startswith("No setup from"):
        return "no_setup_unclassified"
    if any(word in lowered for word in ("weekend", "session", "overlap")):
        return "session_filter"
    if any(word in lowered for word in ("regime", "adx", "atr percentile")):
        return "regime_filter"
    if any(word in lowered for word in ("breakout", "retest")):
        return "trigger_not_confirmed"
    if any(word in lowered for word in ("history", "bars")):
        return "insufficient_history"
    return reason[:80]


scanner_decisions = ScannerDecisionStore()
