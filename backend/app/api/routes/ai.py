"""AI meta-labeling model management: train (per asset or all) and status."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.ai_engine.model_trainer import train_asset
from app.ai_engine.signal_eval import has_model
from app.core.constants import SUPPORTED_ASSETS
from app.services.mt5_client import mt5_client

router = APIRouter(prefix="/ai", tags=["ai"])


class TrainRequest(BaseModel):
    assets: list[str] | None = None   # None = all supported
    timeframe: str = "H1"
    count: int = 5000
    horizon: int = 5


@router.post("/train")
def train(req: TrainRequest) -> dict:
    assets = req.assets or list(SUPPORTED_ASSETS)
    results = []
    for asset in assets:
        df = mt5_client.fetch_ohlcv(asset, req.timeframe, req.count)
        results.append(train_asset(asset, df, horizon=req.horizon))
    return {"results": results}


@router.get("/status")
def status() -> dict:
    return {a: {"model_trained": has_model(a)} for a in SUPPORTED_ASSETS}
