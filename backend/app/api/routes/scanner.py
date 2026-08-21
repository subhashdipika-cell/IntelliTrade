"""Auto-scanner control: deployed assets/strategy/timeframe, on/off, and the
alert-only vs autonomous mode toggle."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.scanner_store import VALID_MODES, scanner_settings
from app.services.scanner_decision_store import scanner_decisions
from app.strategies.registry import list_strategies
from app.workers.signal_scanner import signal_scanner

router = APIRouter(prefix="/scanner", tags=["scanner"])


class ScannerPatch(BaseModel):
    enabled: bool | None = None
    mode: str | None = None            # "alert_only" | "autonomous"
    assets: list[str] | None = None
    strategies: list[str] | None = None
    timeframe: str | None = None
    wiki_enabled: bool | None = None
    # Per-asset override of `strategies` (backtest-driven selection)
    strategies_by_asset: dict[str, list[str]] | None = None


@router.get("/settings")
def get_settings() -> dict:
    return {
        "settings": asdict(scanner_settings.get()),
        "valid_modes": list(VALID_MODES),
        "strategies": list_strategies(),
    }


@router.put("/settings")
def update_settings(patch: ScannerPatch) -> dict:
    return asdict(scanner_settings.update(**patch.model_dump(exclude_none=True)))


@router.get("/status")
def status() -> dict:
    return signal_scanner.status()


@router.get("/decisions")
def decisions(limit: int = 100, asset: str | None = None,
              strategy: str | None = None, status: str | None = None) -> dict:
    rows = scanner_decisions.recent(
        limit=limit, asset=asset, strategy=strategy, status=status,
    )
    return {"count": len(rows), "decisions": rows}


@router.get("/blockers")
def blockers(hours: int = 24) -> dict:
    return scanner_decisions.blocker_summary(hours=hours)


@router.get("/diagnostics")
def diagnostics(hours: int = 24) -> dict:
    return scanner_decisions.blocker_summary(hours=hours)
