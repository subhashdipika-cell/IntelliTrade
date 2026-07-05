"""Telegram test + status endpoints, so you can confirm alerts work from the
Settings page before risking a live signal."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.pipeline.context import Direction, Outcome, Signal
from app.services import telegram

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.get("/status")
def status() -> dict:
    return {
        "enabled": settings.telegram_enabled,
        "configured": settings.telegram_configured,
    }


@router.post("/test-entry")
def test_entry() -> dict:
    demo = Signal("GOLD", Direction.BUY, entry=2340.50, stop_loss=2330.00,
                  target=2361.50, timeframe="H1", lots=0.10)
    ok = telegram.send_entry_alert(demo, capital_deployed=234.05, total_capital=10_450.00)
    return {"sent": ok}


@router.post("/test-exit")
def test_exit() -> dict:
    ok = telegram.send_exit_alert("GOLD", Outcome.TGT, final_capital=10_595.50, pnl=145.50)
    return {"sent": ok}
