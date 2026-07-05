"""Live pipeline trigger. POST a signal-evaluation request for an asset; the
pipeline runs Market→...→Execution and returns the full decision tree."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.constants import SUPPORTED_ASSETS
from app.pipeline.factory import build_pipeline
from app.pipeline.context import Decision, Direction, Signal, TradeContext, Verdict
from app.pipeline.stages.execution import ExecutionStage
from app.services.mt5_client import mt5_client
from app.services.trade_store import open_trades

router = APIRouter(prefix="/live", tags=["live"])


class RunRequest(BaseModel):
    asset: str = "GOLD"
    timeframe: str = "H1"
    strategy: str = "sma_crossover"
    wiki_enabled: bool = True
    # Lot size / daily-loss limit / override now come from persisted Money Mgmt
    # settings. Only the live daily-loss tally is a per-run input.
    daily_loss_pct: float = 0.0


@router.get("/assets")
def assets() -> dict:
    from app.strategies.registry import list_strategies
    return {"assets": list(SUPPORTED_ASSETS), "strategies": list_strategies()}


class TestTradeRequest(BaseModel):
    asset: str = "GOLD"
    direction: str = "BUY"


@router.post("/test-trade")
def test_trade(req: TestTradeRequest) -> dict:
    """Place a minimum-lot DEMO order with a tight valid SL/TP bracket so the full
    loop (order → entry alert → monitor → close → exit alert → History) can be
    exercised on demand. Hard-blocked unless the terminal reports DEMO."""
    actual = mt5_client.verify_account_type()
    if actual != "DEMO":
        return {"status": "BLOCKED",
                "reason": f"Test trade allowed on DEMO only (terminal reports '{actual}')."}

    spec = mt5_client.symbol_spec(req.asset)
    if spec is None:
        return {"status": "ERROR", "reason": "Symbol spec unavailable (MT5 connected?)."}

    point, digits = spec["point"], spec["digits"]
    is_buy = req.direction.upper() == "BUY"
    price = spec["ask"] if is_buy else spec["bid"]
    # Bracket must clear the broker min-stop AND the spread, but also be wide
    # enough (>=0.2% of price) that it doesn't trigger instantly — so you can
    # watch it open and close it deliberately.
    broker_min = (spec["stops_level"] + spec["spread"] * 2) * point
    dist = max(broker_min, price * 0.002)
    sl = round(price - dist if is_buy else price + dist, digits)
    tp = round(price + dist if is_buy else price - dist, digits)
    lots = spec["volume_min"]

    sig = Signal(req.asset.upper(), Direction.BUY if is_buy else Direction.SELL,
                 entry=round(price, digits), stop_loss=sl, target=tp, lots=lots)
    ctx = TradeContext(asset=req.asset.upper())
    ctx.signal = sig
    acct = mt5_client.account_info()
    ctx.total_capital = acct["equity"] if acct else None
    margin = mt5_client.calc_margin(req.asset, sig.direction.value, lots, price)
    ctx.capital_deployed = round(margin, 2) if margin else round(price * lots, 2)
    ctx.record(Decision("test-trade", Verdict.INFO,
                        f"Manual DEMO test: {sig.direction.value} {lots} lot {req.asset}, "
                        f"bracket ±{dist:.{digits}f}"))

    ExecutionStage().process(ctx)
    return {
        "status": "BLOCKED" if ctx.blocked else "EXECUTED",
        "ticket": ctx.ticket,
        "signal": {"direction": sig.direction.value, "entry": sig.entry,
                   "sl": sig.stop_loss, "tp": sig.target, "lots": sig.lots},
        "capital_deployed": ctx.capital_deployed,
        "decision_tree": ctx.explain(),
    }


@router.get("/monitored")
def monitored() -> dict:
    """Open trades the monitor worker is watching for close (exit-alert queue)."""
    tickets = open_trades.tickets()
    return {
        "count": len(tickets),
        "tickets": sorted(tickets),
        "trades": [
            {
                "ticket": t,
                "asset": ctx.asset,
                "direction": ctx.signal.direction.value if ctx.signal else None,
                "entry": ctx.signal.entry if ctx.signal else None,
            }
            for t in sorted(tickets)
            if (ctx := open_trades.get(t)) is not None
        ],
    }


@router.post("/run")
def run(req: RunRequest) -> dict:
    # risk_config defaults to the persisted Money Mgmt settings inside the factory.
    pipeline = build_pipeline(
        strategy_name=req.strategy,
        wiki_enabled=req.wiki_enabled,
        daily_loss_pct=req.daily_loss_pct,
    )
    ctx = pipeline.run(TradeContext(asset=req.asset.upper(), timeframe=req.timeframe))
    return {
        "asset": ctx.asset,
        "blocked": ctx.blocked,
        "blocked_by": ctx.blocked_by,
        "ticket": ctx.ticket,
        "signal": None if ctx.signal is None else {
            "direction": ctx.signal.direction.value,
            "entry": ctx.signal.entry,
            "sl": ctx.signal.stop_loss,
            "tp": ctx.signal.target,
            "lots": ctx.signal.lots,
        },
        "decision_tree": ctx.explain(),
    }
