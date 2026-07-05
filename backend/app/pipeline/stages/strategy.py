"""Strategy stage — runs the active strategy to (maybe) produce a Signal.

Holds a reference to a Strategy object (see app/strategies). If no signal fires
this bar, the pipeline is blocked with a benign 'no setup' reason. After a signal
fires, the target is capped to the nearest swing structure (so we don't aim past
a wall) when that guardrail is enabled in Money Mgmt."""
from __future__ import annotations

from app.pipeline.base import Stage
from app.pipeline.context import Decision, TradeContext, Verdict
from app.strategies import indicators as ind
from app.strategies.base import Strategy


class StrategyStage(Stage):
    name = "strategy"

    def __init__(self, strategy: Strategy) -> None:
        super().__init__()
        self.strategy = strategy

    def process(self, ctx: TradeContext) -> TradeContext:
        ctx.strategy = self.strategy.name
        signal = self.strategy.generate(ctx.asset, ctx.market_data, ctx.timeframe)
        if signal is None:
            ctx.record(Decision(self.name, Verdict.BLOCK,
                                f"No setup from '{self.strategy.name}'."))
            return ctx
        ctx.signal = signal
        ctx.record(Decision(
            self.name, Verdict.PASS,
            f"{self.strategy.name}: {signal.direction.value} @ {signal.entry:g}",
        ))
        self._cap_target_to_structure(ctx)
        return ctx

    def _cap_target_to_structure(self, ctx: TradeContext) -> None:
        """Pull the target inside the nearest resistance/support so we don't aim
        past a wall (the 'target above resistance' failure). Records the result on
        the decision tree; can BLOCK if the post-cap RR is too poor (opt-in)."""
        from app.services.settings_store import money_settings

        cfg = money_settings.get()
        if not cfg.target_cap_enabled or ctx.market_data is None:
            return
        sig = ctx.signal
        df = ctx.market_data
        if df is None or len(df) < 2:
            return
        a = float(ind.atr(df, 14).iloc[-1])
        if a != a or a <= 0:  # NaN / zero ATR — nothing to base a buffer on
            return

        new_tp, level, rr_after = ind.cap_target_to_structure(
            sig.direction.value, sig.entry, sig.stop_loss, sig.target, df,
            a, lookback=cfg.resistance_lookback,
        )
        if level is None or new_tp == sig.target:
            return  # no wall in the way — original target stands

        if cfg.skip_low_rr and rr_after < cfg.min_rr_after_cap:
            ctx.record(Decision(
                self.name, Verdict.BLOCK,
                f"Target capped at structure {level:g} → RR {rr_after:.2f} "
                f"< {cfg.min_rr_after_cap:g} floor. Skipping (buying into resistance).",
            ))
            return
        sig.target = new_tp
        ctx.record(Decision(
            self.name, Verdict.INFO,
            f"Target capped {sig.target:g} (below structure {level:g}); "
            f"RR now {rr_after:.2f}.",
        ))
