"""Strategy Review — LLM-assisted analysis of live strategy performance.

GET /api/review/strategies runs the review on demand (the LLM call can be slow,
especially on a local Ollama model, so the UI shows a loading state). Read-only."""
from __future__ import annotations

from fastapi import APIRouter

from app.services import strategy_review

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/strategies")
def strategies() -> dict:
    return strategy_review.review()
