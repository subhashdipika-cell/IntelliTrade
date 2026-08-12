"""Governed AI meta-labeling filter."""
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
        from app.ai_engine.model_trainer import model_metadata
        from app.core.config import settings
        if settings.ai_ensemble_enabled:
            result = self._ensemble(ctx)
            if not result.available:
                verdict = Verdict.BLOCK if settings.ai_ensemble_blocking else Verdict.INFO
                ctx.record(Decision(self.name, verdict,
                                    f"AI ensemble unavailable: {result.reason}"))
                return ctx
            confidence = result.score
            ctx.record(Decision(self.name, Verdict.INFO,
                                f"HF ensemble score {confidence:.0%}; "
                                f"direct={result.direct:.0%}, foundation={result.foundation:.0%}, "
                                f"sentiment={result.sentiment:.0%}, agreement={result.agreement:.0%}, "
                                f"uncertainty={result.uncertainty:.0%}.", score=confidence))
            if settings.ai_ensemble_blocking and confidence < self.min_confidence:
                ctx.record(Decision(self.name, Verdict.BLOCK,
                                    f"HF ensemble confidence {confidence:.0%} < "
                                    f"{self.min_confidence:.0%}.", score=confidence))
            return ctx

        confidence = self._score(ctx)
        if not model_metadata(ctx.asset).get("active"):
            ctx.record(Decision(self.name,
                                Verdict.INFO,
                                f"Advisory confidence {confidence:.0%}; no validated outcome model.",
                                score=confidence))
            return ctx
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

    def _ensemble(self, ctx: TradeContext):
        from app.ai_engine.hf_ensemble import evaluate_ensemble
        sig = ctx.signal
        return evaluate_ensemble(
            ctx.asset, ctx.market_data, sig.direction.value, ctx.strategy,
            ctx.timeframe, sig.entry, sig.stop_loss, sig.target,
        )

    def _score(self, ctx: TradeContext) -> float:
        from app.ai_engine.signal_eval import predict_win_probability

        if ctx.market_data is None or len(ctx.market_data) == 0:
            return 1.0
        direction = ctx.signal.direction.value if ctx.signal else "BUY"
        return predict_win_probability(ctx.asset, ctx.market_data, direction,
                                       ctx.strategy, ctx.timeframe,
                                       ctx.signal.entry, ctx.signal.stop_loss,
                                       ctx.signal.target)
