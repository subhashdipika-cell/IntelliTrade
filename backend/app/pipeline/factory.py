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


def parse_rr_ratio(raw: str | float | None) -> float | None:
    """Money-Mgmt `rr_ratio` -> reward multiple. Accepts "1:2" / "1:2.5" / 2.5.

    Until 2026-07-19 this setting was DECORATIVE: nothing read it, so every
    strategy used its own hardcoded `rr` (1.5-2.0) and the UI value was a lie.
    The 95-trade review made that costly - a 25% win rate needs ~3:1 to break
    even, while the book was running ~1.75.
    """
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            rr = float(raw)
        else:
            txt = str(raw).strip()
            rr = float(txt.split(":")[1]) / float(txt.split(":")[0]) if ":" in txt else float(txt)
        return rr if rr > 0 else None
    except (ValueError, ZeroDivisionError, IndexError):
        return None


def build_pipeline(
    strategy: Strategy | None = None,
    *,
    strategy_name: str = "sma_crossover",
    wiki_enabled: bool = True,
    wiki_blocking: bool = False,
    ai_blocking: bool = True,
    risk_config: RiskConfig | None = None,
    daily_loss_pct: float = 0.0,
    include_execution: bool = True,
) -> Pipeline:
    # Live signals inherit the Money-Mgmt reward multiple; a strategy passed in
    # ready-made (backtests, explicit params) is left exactly as the caller
    # built it, so research stays reproducible.
    if strategy is None:
        rr = parse_rr_ratio(money_settings.get().rr_ratio)
        strategy = build_strategy(strategy_name, {"rr": rr} if rr else None)
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
