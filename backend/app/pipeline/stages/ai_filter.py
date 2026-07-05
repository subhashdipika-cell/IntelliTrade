"""AI meta-labeling filter.

Deliberately ADVISORY by default: it scores the signal and records an INFO
decision, but does NOT block until you have enough live trade history for the
model to be trustworthy. Flip `blocking=True` and set `min_confidence` only once
the model is validated. The edge must come from strategy + risk, not this."""
from __future__ import annotations

from app.pipeline.base import Stage
from app.pipeline.context import Decision, TradeContext, Verdict


class AIFilterStage(Stage):
    name = "ai_filter"

    def __init__(self, blocking: bool = False, min_confidence: float = 0.60) -> None:
        super().__init__()
        self.blocking = blocking
        self.min_confidence = min_confidence

    def process(self, ctx: TradeContext) -> TradeContext:
        if ctx.signal is None:
            ctx.record(Decision(self.name, Verdict.SKIP, "No signal to score."))
            return ctx
        confidence = self._score(ctx)
        if not self.blocking:
            ctx.record(Decision(self.name, Verdict.INFO,
                                f"Advisory confidence {confidence:.0%}.",
                                score=confidence))
        elif confidence < self.min_confidence:
            ctx.record(Decision(self.name, Verdict.BLOCK,
                                f"Confidence {confidence:.0%} < {self.min_confidence:.0%}.",
                                score=confidence))
        else:
            ctx.record(Decision(self.name, Verdict.PASS,
                                f"Confidence {confidence:.0%}.", score=confidence))
        return ctx

    def _score(self, ctx: TradeContext) -> float:
        from app.ai_engine.signal_eval import predict_win_probability

        if ctx.market_data is None or len(ctx.market_data) == 0:
            return 1.0
        direction = ctx.signal.direction.value if ctx.signal else "BUY"
        return predict_win_probability(ctx.asset, ctx.market_data, direction)
