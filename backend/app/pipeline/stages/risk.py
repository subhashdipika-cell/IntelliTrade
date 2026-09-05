"""Risk / money-management stage.

Sizes the position, computes capital deployed, and enforces the daily-loss
hard-stop — which can be overridden by the user's Money-Mgmt toggle."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.pipeline.base import Stage
from app.pipeline.context import Decision, TradeContext, Verdict
from app.services import gold_hours
from app.services.daily_stats import daily_realized_stats
from app.services.mt5_client import mt5_client


@dataclass
class RiskConfig:
    base_lots: float = 0.10              # fallback for assets not in lots_by_asset
    lots_by_asset: dict[str, float] = field(default_factory=dict)
    risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 2.0
    hard_stop_override: bool = False
    profit_lock_enabled: bool = True
    profit_lock_pct: float = 1.0         # bank the day at +N% of balance (0 = off)
    profit_giveback_pct: float = 50.0    # lock when day P&L falls this % off its peak (0 = off)
    contract_value_per_lot: float = 1.0  # rough notional per lot per price unit

    def lots_for(self, asset: str) -> float:
        return float(self.lots_by_asset.get((asset or "").upper(), self.base_lots))


class RiskStage(Stage):
    name = "risk"

    def __init__(self, config: RiskConfig, daily_loss_pct: float = 0.0) -> None:
        super().__init__()
        self.cfg = config
        self.daily_loss_pct = daily_loss_pct  # supplied by the day's running tally

    def process(self, ctx: TradeContext) -> TradeContext:
        if ctx.signal is None:
            ctx.record(Decision(self.name, Verdict.SKIP, "No signal to size."))
            return ctx

        # Daily-loss hard stop (with override).
        if self.daily_loss_pct >= self.cfg.max_daily_loss_pct:
            if self.cfg.hard_stop_override:
                ctx.record(Decision(self.name, Verdict.INFO,
                                    f"Daily loss {self.daily_loss_pct:.1f}% breached but "
                                    f"override ACTIVE — proceeding."))
            else:
                ctx.record(Decision(self.name, Verdict.BLOCK,
                                    f"Daily loss {self.daily_loss_pct:.1f}% >= "
                                    f"{self.cfg.max_daily_loss_pct:.1f}% hard stop."))
                return ctx

        # Daily PROFIT lock — don't hand the day's gains back through fresh
        # trades' SLs. Deliberately NOT subject to the manual override: banking
        # the day is the whole point of the rule. Open positions are untouched
        # (monitor keeps trailing them); only NEW entries are blocked.
        if self.cfg.profit_lock_enabled and self.cfg.profit_lock_pct > 0:
            stats = daily_realized_stats()
            bal = stats.get("balance")
            if bal:
                target = bal * self.cfg.profit_lock_pct / 100.0
                if stats["pnl"] >= target:
                    ctx.record(Decision(self.name, Verdict.BLOCK,
                                        f"Profit lock: today +{stats['pnl']:.2f} >= target "
                                        f"+{target:.2f} ({self.cfg.profit_lock_pct:g}% of balance) "
                                        f"— day banked, no new entries."))
                    return ctx
                # Give-back stop: arms once the day has peaked at ≥ half the
                # target; locks if the running total falls too far off that peak.
                if (self.cfg.profit_giveback_pct > 0 and stats["peak"] >= target / 2
                        and stats["pnl"] <= stats["peak"] * (1 - self.cfg.profit_giveback_pct / 100.0)):
                    ctx.record(Decision(self.name, Verdict.BLOCK,
                                        f"Give-back stop: day peaked +{stats['peak']:.2f}, now "
                                        f"+{stats['pnl']:.2f} (≥{self.cfg.profit_giveback_pct:g}% "
                                        f"given back) — locking what's left."))
                    return ctx

        # Friday gold cutoff — no new gold entries after 21:45 IST. Vantage can
        # close XAUUSD+ at 22:30 IST on US-holiday Fridays (unannounced); the
        # trade monitor flattens open gold at 22:15 IST. See services/gold_hours.
        if ctx.signal is not None and gold_hours.is_gold(ctx.signal.asset):
            block_gold, _ = gold_hours.friday_state()
            if block_gold:
                ctx.record(Decision(self.name, Verdict.BLOCK,
                                    "Friday gold cutoff — no new gold entries after 21:45 IST "
                                    "(early 22:30 IST close risk on US-holiday Fridays)."))
                return ctx

        acct = mt5_client.account_info()
        total_capital = acct["equity"] if acct else None
        ctx.total_capital = total_capital

        configured_cap = self.cfg.lots_for(ctx.signal.asset)
        lots, risk_reason = self._risk_sized_lots(ctx, configured_cap)
        if lots is None:
            ctx.record(Decision(self.name, Verdict.BLOCK, risk_reason))
            return ctx
        ctx.signal.lots = lots
        margin = mt5_client.calc_margin(
            ctx.signal.asset, ctx.signal.direction.value, lots, ctx.signal.entry,
        )
        ctx.capital_deployed = round(margin, 2) if margin is not None else self._estimate_capital(
            ctx.signal.entry, lots,
        )

        ctx.record(Decision(self.name, Verdict.PASS,
                            f"{risk_reason}; sized {lots:g} lots for {ctx.signal.asset} "
                            f"(~deployed {ctx.capital_deployed:.2f})."))
        return ctx

    def _risk_sized_lots(self, ctx: TradeContext, configured_cap: float) -> tuple[float | None, str]:
        """Size from stop distance and equity, with configured lots as a hard cap."""
        sig = ctx.signal
        spec = mt5_client.symbol_spec(sig.asset)
        if spec is None or not ctx.total_capital:
            return None, "Broker risk sizing unavailable; order refused"

        tick_size = float(spec.get("trade_tick_size") or spec.get("point") or 0)
        tick_value = float(spec.get("trade_tick_value_loss") or 0)
        step = float(spec.get("volume_step") or spec.get("volume_min") or 0.01)
        minimum = float(spec.get("volume_min") or step)
        maximum = float(spec.get("volume_max") or configured_cap)
        market_entry = float(spec["ask"] if sig.direction.value == "BUY" else spec["bid"])
        stop_distance = abs(market_entry - float(sig.stop_loss))
        risk_per_lot = (stop_distance / tick_size) * tick_value if tick_size > 0 else 0
        budget = float(ctx.total_capital) * self.cfg.risk_per_trade_pct / 100.0
        if risk_per_lot <= 0 or budget <= 0:
            return None, "Invalid stop-risk inputs; order refused"

        raw = min(budget / risk_per_lot, configured_cap, maximum)
        lots = math.floor((raw + 1e-12) / step) * step
        decimals = max(0, len(f"{step:.10f}".rstrip("0").split(".")[-1]))
        lots = round(lots, decimals)
        if lots < minimum:
            min_risk = minimum * risk_per_lot
            return None, (
                f"Minimum {minimum:g} lot risks ~{min_risk:.2f}, above "
                f"{self.cfg.risk_per_trade_pct:g}% budget {budget:.2f}; order refused"
            )
        estimated_risk = lots * risk_per_lot
        return lots, (
            f"stop-risk ~{estimated_risk:.2f}/{budget:.2f} budget "
            f"({self.cfg.risk_per_trade_pct:g}% equity, cap {configured_cap:g})"
        )

    def _estimate_capital(self, entry: float, lots: float) -> float:
        return round(entry * lots * self.cfg.contract_value_per_lot, 2)
