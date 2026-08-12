"""Economic-events endpoint for the dashboard ticker."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.economic_calendar import get_events

router = APIRouter(prefix="/news", tags=["news"])


class SentimentRequest(BaseModel):
    text: str
    asset: str = "MACRO"
    source: str = "api"


@router.get("/events")
def events(impact: str = "High", currencies: str = "USD") -> dict:
    cur = tuple(c.strip().upper() for c in currencies.split(",") if c.strip())
    return get_events(impact=impact, currencies=cur)


@router.post("/sentiment")
def sentiment(req: SentimentRequest) -> dict:
    from app.ai_engine.sentiment_service import score_text
    return score_text(req.text, req.asset, req.source)
