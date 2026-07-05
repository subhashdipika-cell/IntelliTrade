"""Assembles the default pipeline. One place to wire stage order + toggles."""
from __future__ import annotations

from app.pipeline.runner import Pipeline
from app.pipeline.stages.ai_filter import AIFilterStage
from app.pipeline.stages.execution import ExecutionStage
from app.pipeline.stages.market import MarketStage
from app.pipeline.stages.risk import RiskConfig, RiskStage
from app.pipeline.stages.strategy import StrategyStage
from app.pipeline.stages.wiki_filter import WikiFilterStage
from app.services.settings_store import money_settings
from app.strategies.base import Strategy
from app.strategies.registry import build_strategy


def build_pipeline(
    strategy: Strategy | None = None,
    *,
    strategy_name: str = "sma_crossover",
    wiki_enabled: bool = True,
    wiki_blocking: bool = False,
    ai_blocking: bool = False,
    risk_config: RiskConfig | None = None,
    daily_loss_pct: float = 0.0,
    include_execution: bool = True,
) -> Pipeline:
    strategy = strategy or build_strategy(strategy_name)
    # Default risk config comes from the persisted Money Mgmt settings.
    if risk_config is None:
        s = money_settings.get()
        risk_config = RiskConfig(
            base_lots=s.base_lots,
            lots_by_asset=dict(s.lots_by_asset),
            risk_per_trade_pct=s.risk_per_trade_pct,
            max_daily_loss_pct=s.max_daily_loss_pct,
            hard_stop_override=s.hard_stop_override,
            profit_lock_enabled=s.profit_lock_enabled,
            profit_lock_pct=s.profit_lock_pct,
            profit_giveback_pct=s.profit_giveback_pct,
        )
    stages = [
        MarketStage(),
        StrategyStage(strategy),
        AIFilterStage(blocking=ai_blocking),
        WikiFilterStage(enabled=wiki_enabled, blocking=wiki_blocking),
        RiskStage(risk_config, daily_loss_pct=daily_loss_pct),
    ]
    if include_execution:
        stages.append(ExecutionStage())
    return Pipeline(stages)
