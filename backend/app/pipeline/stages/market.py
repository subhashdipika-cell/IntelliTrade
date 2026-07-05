"""Market stage — pull fresh OHLCV for the asset onto the context."""
from __future__ import annotations

from app.pipeline.base import Stage
from app.pipeline.context import Decision, TradeContext, Verdict
from app.services.mt5_client import mt5_client


class MarketStage(Stage):
    name = "market"

    def __init__(self, count: int = 2000) -> None:
        super().__init__()
        self.count = count

    def process(self, ctx: TradeContext) -> TradeContext:
        if ctx.market_data is None or len(ctx.market_data) == 0:
            ctx.market_data = mt5_client.fetch_ohlcv(ctx.asset, ctx.timeframe, self.count)
        bars = 0 if ctx.market_data is None else len(ctx.market_data)
        if bars == 0:
            ctx.record(Decision(self.name, Verdict.BLOCK, "No market data available."))
        else:
            ctx.record(Decision(self.name, Verdict.PASS, f"Loaded {bars} bars."))
        return ctx
