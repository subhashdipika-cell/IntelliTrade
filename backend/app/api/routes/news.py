"""Economic-events endpoint for the dashboard ticker."""
from __future__ import annotations

from fastapi import APIRouter

from app.services.economic_calendar import get_events

router = APIRouter(prefix="/news", tags=["news"])


@router.get("/events")
def events(impact: str = "High", currencies: str = "USD") -> dict:
    cur = tuple(c.strip().upper() for c in currencies.split(",") if c.strip())
    return get_events(impact=impact, currencies=cur)
