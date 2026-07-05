"""Runs a TradeContext through the ordered stages, halting on the first BLOCK
(unless that stage is advisory). The order IS the architecture:

    Market → Analysis → Strategy → AI Filter → Wiki Filter → Risk → Execution

Monitoring + Learning run on separate schedules, not inline with signal birth.
"""
from __future__ import annotations

from app.core.logging_setup import get_logger
from app.pipeline.base import Stage
from app.pipeline.context import TradeContext

log = get_logger("pipeline.runner")


class Pipeline:
    def __init__(self, stages: list[Stage]) -> None:
        self.stages = stages

    def run(self, ctx: TradeContext) -> TradeContext:
        for stage in self.stages:
            ctx = stage.process(ctx)
            last = ctx.decisions[-1] if ctx.decisions else None
            if last:
                log.info(
                    "%s -> %s (%s)", stage.name, last.verdict.value, last.reason
                )
            if ctx.blocked:
                log.info("Pipeline halted at '%s'.", ctx.blocked_by)
                break
        return ctx
