"""Obsidian Wiki (RAG) gatekeeper.

Two toggles drive this stage:
  - enabled   : whether to consult the wiki at all (your dashboard toggle)
  - blocking  : whether a 'no' from the LLM actually halts the trade. Keep this
                False (advisory) until you trust the retrieval + prompt, because
                a non-deterministic LLM blocking a fast move costs real money."""
from __future__ import annotations

from app.pipeline.base import Stage
from app.pipeline.context import Decision, TradeContext, Verdict


class WikiFilterStage(Stage):
    name = "wiki_filter"

    def __init__(self, enabled: bool = True, blocking: bool = False) -> None:
        super().__init__()
        self.enabled = enabled
        self.blocking = blocking

    def process(self, ctx: TradeContext) -> TradeContext:
        if not self.enabled:
            ctx.record(Decision(self.name, Verdict.SKIP, "Wiki screening disabled."))
            return ctx
        if ctx.signal is None:
            ctx.record(Decision(self.name, Verdict.SKIP, "No signal to validate."))
            return ctx

        approved, reason = self._validate(ctx)
        if not self.blocking:
            ctx.record(Decision(self.name, Verdict.INFO,
                                f"Advisory: {'approve' if approved else 'flag'} — {reason}"))
        elif not approved:
            ctx.record(Decision(self.name, Verdict.BLOCK, f"Blocked by wiki: {reason}"))
        else:
            ctx.record(Decision(self.name, Verdict.PASS, f"Wiki approved: {reason}"))
        return ctx

    def _validate(self, ctx: TradeContext) -> tuple[bool, str]:
        from app.obsidian_rag import wiki_validator

        sig = ctx.signal
        return wiki_validator.validate(
            asset=sig.asset, direction=sig.direction.value,
            entry=sig.entry, sl=sig.stop_loss, tp=sig.target, timeframe=sig.timeframe,
        )
