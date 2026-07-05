"""Trailing-stop manager — protects open profit on tracked trades.

Runs on the monitor poll (every POLL_SECONDS). For each still-open IntelliTrade
position it computes how far price has travelled toward the target and, in three
ratcheting stages, moves the broker-side stop:

  1. Breakeven   — at `be_trigger_pct`% of the way to TP, SL → entry (+buffer).
  2. Trail       — beyond `trail_trigger_pct`%, SL trails the best price by
                   `trail_r_mult` × R.
  3. Near-target — beyond `near_target_pct`% (the zone where runners reverse),
                   tighten to `near_target_r_mult` × R so most of the gain is kept.

R = |entry - original SL| (initial risk). Triggers are % of distance-to-target so
they still arm when a trade's RR < 1. The stop only ever tightens (ratchet); the
original `signal.stop_loss` is left untouched so the close still classifies as TSL.
"""
from __future__ import annotations

from app.core.logging_setup import get_logger
from app.pipeline.context import Direction, TradeContext
from app.services.mt5_client import mt5_client
from app.services.settings_store import money_settings

log = get_logger("services.trailing")


def _desired_stop(ctx: TradeContext, best: float, cfg) -> tuple[float | None, str | None]:
    """Compute the stop the trail wants given the best price so far, or (None, None)
    if no stage has armed yet. Direction-aware."""
    sig = ctx.signal
    entry, sl0, tp = sig.entry, sig.stop_loss, sig.target
    R = abs(entry - sl0)
    D = abs(tp - entry)
    if R <= 0 or D <= 0:
        return None, None

    is_buy = sig.direction is Direction.BUY
    progress = (best - entry) / D if is_buy else (entry - best) / D

    if progress >= cfg.near_target_pct / 100.0:
        give = cfg.near_target_r_mult * R
        return (best - give if is_buy else best + give), "NEAR"
    if progress >= cfg.trail_trigger_pct / 100.0:
        give = cfg.trail_r_mult * R
        return (best - give if is_buy else best + give), "TRAIL"
    if progress >= cfg.be_trigger_pct / 100.0:
        buf = cfg.be_buffer_r * R
        return (entry + buf if is_buy else entry - buf), "BE"
    return None, None


def update_trade(ctx: TradeContext) -> bool:
    """Re-evaluate the trailing stop for one open trade. Returns True if the
    broker stop was moved this poll. Never raises (logs + returns False)."""
    cfg = money_settings.get()
    if not cfg.trailing_enabled or ctx.signal is None or ctx.ticket is None:
        return False

    sig = ctx.signal
    spec = mt5_client.symbol_spec(sig.asset)
    if spec is None:
        return False  # stub / not connected

    is_buy = sig.direction is Direction.BUY
    # Price we'd actually close on (exit side): BUY closes at bid, SELL at ask.
    price = spec["bid"] if is_buy else spec["ask"]

    # Track the most-favorable excursion.
    if ctx.mfe_price is None:
        ctx.mfe_price = sig.entry
    ctx.mfe_price = max(ctx.mfe_price, price) if is_buy else min(ctx.mfe_price, price)

    desired, stage = _desired_stop(ctx, ctx.mfe_price, cfg)
    if desired is None:
        return False

    # Ratchet only — never loosen. Compare against the live trailed stop (or the
    # original SL if we've not moved it yet).
    cur = ctx.current_sl if ctx.current_sl is not None else sig.stop_loss
    improves = desired > cur if is_buy else desired < cur
    if not improves:
        return False

    res = mt5_client.modify_position(ctx.ticket, sl=desired, tp=sig.target)
    if not res.get("ok"):
        log.warning("Trail modify failed for ticket %s: %s", ctx.ticket, res.get("reason"))
        return False

    ctx.current_sl = res.get("sl", desired)
    ctx.trail_stage = stage
    log.info("Trailed ticket %s [%s]: SL -> %.5f (mfe=%.5f)",
             ctx.ticket, stage, ctx.current_sl, ctx.mfe_price)
    return True
