"""Level engine — context awareness ("human touch") for the signal pipeline.

Complements the existing swing target-cap (StrategyStage._cap_target_to_structure)
with the full level map and the entry-side checks it doesn't cover:

  freshness        : skip when price is already > ext_max_atr ATR beyond its 20-EMA
                     in the trade direction (the move already happened — chasing)
  location         : no BUY right under a wall / no SELL right above one
  R:R to structure : (room to the nearest strong opposing level − buffer) / risk
                     must be ≥ min_rr_structure
  richer target cap: PDH/PDL and round numbers can be tighter walls than the
                     swing window — cap the target to those too

Level map = fractal swings + previous-day high/low + round numbers (majors are
walls, minors are context). Everything is recorded on the TradeContext decision
tree, so History/Replay answers "why was this skipped?".

Config: backend/level_config.json (optional).
  {"enforce": false} → shadow mode: violations are recorded as INFO, nothing blocks.
"""
from __future__ import annotations

import json
import os

import pandas as pd

from app.pipeline.context import Decision, TradeContext, Verdict
from app.strategies import indicators as ind

CONFIG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "level_config.json"))

DEFAULTS = {
    "enforce": True,          # False = shadow (record, don't block)
    "min_rr_structure": 1.2,
    "buffer_atr": 0.25,
    "loc_atr": 0.35,
    "ext_max_atr": 1.5,
    "min_barrier_strength": 1.0,
}

# (minor step, major step) — majors are walls (1.2), minors context (0.6).
ROUND_STEPS = {"BTC": (500, 1000), "ETH": (50, 100), "GOLD": (10, 50)}


def get_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE) as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def build_level_map(df: pd.DataFrame, asset: str) -> dict:
    """Swings + previous-day H/L + rounds from the OHLCV frame (DatetimeIndex)."""
    if df is None or len(df) < 60:
        return {"ok": False}
    highs = df["high"].astype(float).tolist()
    lows = df["low"].astype(float).tolist()
    closes = df["close"].astype(float).tolist()
    spot = closes[-1]
    a = float(ind.atr(df, 14).iloc[-1])
    if a != a or a <= 0:
        a = spot * 0.002

    raw: list[dict] = []
    # Fractal swings (strictly higher/lower than 3 bars each side), last 8 each,
    # excluding the forming bar so a breakout isn't walled by itself.
    lb, n = 3, len(highs) - 1
    sh, sl = [], []
    for i in range(max(lb, n - 120), n - lb):
        if all(highs[i] > highs[j] for j in range(i - lb, i + lb + 1) if j != i):
            sh.append(highs[i])
        if all(lows[i] < lows[j] for j in range(i - lb, i + lb + 1) if j != i):
            sl.append(lows[i])
    raw += [{"price": p, "kind": "swing-high", "strength": 1.0} for p in sh[-8:]]
    raw += [{"price": p, "kind": "swing-low", "strength": 1.0} for p in sl[-8:]]

    # Previous-day high/low from the DatetimeIndex.
    try:
        days = pd.Series(df.index.date, index=df.index)
        uniq = sorted(set(days))
        if len(uniq) >= 2:
            mask = (days == uniq[-2]).values
            raw.append({"price": float(df["high"][mask].max()), "kind": "pdh", "strength": 1.3})
            raw.append({"price": float(df["low"][mask].min()), "kind": "pdl", "strength": 1.3})
    except Exception:
        pass

    step, major = ROUND_STEPS.get((asset or "").upper(), (50, 100))
    base = round(spot / step) * step
    for k in range(-3, 4):
        p = base + k * step
        if p > 0:
            raw.append({"price": float(p), "kind": "round",
                        "strength": 1.2 if p % major == 0 else 0.6})

    # Cluster near-identical levels (0.1% of spot), summing strength.
    tol = spot * 0.001
    raw.sort(key=lambda l: l["price"])
    levels: list[dict] = []
    for l in raw:
        if levels and abs(l["price"] - levels[-1]["price"]) <= tol:
            levels[-1]["strength"] = round(levels[-1]["strength"] + l["strength"], 2)
            if l["kind"] not in levels[-1]["kind"]:
                levels[-1]["kind"] += "+" + l["kind"]
        else:
            levels.append(dict(l))
    return {"ok": True, "spot": spot, "atr": a, "levels": levels}


def apply_human_touch(ctx: TradeContext, stage_name: str = "strategy") -> None:
    """Run the context checks on ctx.signal; records decisions (may BLOCK)."""
    cfg = get_config()
    sig = ctx.signal
    df = ctx.market_data
    if sig is None or df is None:
        return
    lm = build_level_map(df, ctx.asset)
    if not lm["ok"]:
        return
    a, spot = lm["atr"], lm["spot"]
    entry = float(sig.entry)
    risk = abs(entry - float(sig.stop_loss))
    is_buy = sig.direction.value == "BUY"
    buffer = cfg["buffer_atr"] * a
    violations: list[str] = []

    # 1) Freshness — extension from the 20-EMA in the trade direction.
    ema20 = float(df["close"].ewm(span=20, adjust=False).mean().iloc[-1])
    ext = (spot - ema20) / a if is_buy else (ema20 - spot) / a
    if ext > cfg["ext_max_atr"]:
        violations.append(
            f"Chasing — price {ext:.1f}xATR beyond the 20-EMA; the move already happened")

    # Nearest strong opposing wall.
    strong = [l for l in lm["levels"] if l["strength"] >= cfg["min_barrier_strength"]]
    eps = spot * 0.0002
    if is_buy:
        opp = [l for l in strong if l["price"] > entry + eps]
        barrier = min(opp, key=lambda l: l["price"]) if opp else None
    else:
        opp = [l for l in strong if l["price"] < entry - eps]
        barrier = max(opp, key=lambda l: l["price"]) if opp else None

    rr_structure = None
    if barrier:
        dist = abs(barrier["price"] - entry)
        # 2) Location.
        if dist <= cfg["loc_atr"] * a:
            violations.append(
                f"{'Longing into resistance' if is_buy else 'Shorting into support'}"
                f" @ {barrier['price']:g} ({barrier['kind']}) only {dist:.5g} away")
        # 3) R:R to structure.
        if risk > 0:
            rr_structure = max(0.0, dist - buffer) / risk
            if rr_structure < cfg["min_rr_structure"]:
                violations.append(
                    f"Only {rr_structure:.2f}R of room to {barrier['price']:g}"
                    f" ({barrier['kind']}) — target would sit beyond structure")

    if violations:
        verdict = Verdict.BLOCK if cfg["enforce"] else Verdict.INFO
        prefix = "" if cfg["enforce"] else "SHADOW would skip: "
        ctx.record(Decision(stage_name, verdict, "Level map: " + prefix + " | ".join(violations)))
        if cfg["enforce"]:
            return

    # 4) Richer target cap — PDH/rounds can be tighter than the swing window.
    if barrier and risk > 0:
        capped = (barrier["price"] - buffer) if is_buy else (barrier["price"] + buffer)
        tighter = (is_buy and capped < float(sig.target)) or (not is_buy and capped > float(sig.target))
        beyond_entry = (capped > entry) if is_buy else (capped < entry)
        if tighter and beyond_entry:
            old = sig.target
            sig.target = round(capped, 5)
            ctx.record(Decision(
                stage_name, Verdict.INFO,
                f"Target re-capped {old:g} -> {sig.target:g} to stay inside "
                f"{barrier['price']:g} ({barrier['kind']}); RR now {abs(sig.target - entry) / risk:.2f}."))

    if rr_structure is not None and not violations:
        ctx.record(Decision(
            stage_name, Verdict.INFO,
            f"Level map OK: {rr_structure:.2f}R of room to {barrier['price']:g} "
            f"({barrier['kind']}); freshness {ext:+.2f}xATR."))
