"""Backtest + walk-forward endpoints."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.backtest.engine import run_backtest
from app.backtest.walk_forward import walk_forward
from app.core.constants import default_commission_per_lot
from app.services import market_data
from app.strategies.registry import build_strategy, list_strategies

router = APIRouter(prefix="/backtest", tags=["backtest"])


def _completed_bars(df, source: str):
    """MT5's last row is the forming candle; research must not use it."""
    return df.iloc[:-1] if source == "mt5" and df is not None and len(df) > 1 else df


@router.get("/strategies")
def strategies() -> dict:
    return {"strategies": list_strategies()}


@router.get("/datasets")
def datasets() -> dict:
    """Imported (offline) datasets available for backtesting."""
    return {"imported": market_data.available()}


@router.post("/import-data")
def import_data() -> dict:
    """Consolidate AlphaEdge's collector CSVs into IntelliTrade's own data dir."""
    return market_data.import_from_alphaedge()


@router.post("/snapshot")
def snapshot() -> dict:
    """Run all strategies × assets and write a regime-tagged snapshot to the
    Obsidian vault now (the scheduler also does this weekly)."""
    from app.services import vault_export
    return vault_export.snapshot_backtests()


class MatrixRequest(BaseModel):
    timeframe: str = "H1"
    count: int = 3000
    initial_capital: float = 1000.0
    source: str = "mt5"  # "mt5" (live) | "imported" (AlphaEdge CSV copy)


@router.post("/matrix")
def matrix(req: MatrixRequest) -> dict:
    """Backtest every strategy on every asset and return a comparison grid — the
    rigorous, immediate answer to 'best strategy per asset'. Each asset's data is
    fetched once and reused across strategies."""
    from app.core.constants import SUPPORTED_ASSETS

    assets = list(SUPPORTED_ASSETS)
    strats = list_strategies()
    grid: dict[str, dict] = {}
    for asset in assets:
        df = _completed_bars(
            market_data.get_ohlcv(asset, req.timeframe, req.count, req.source), req.source,
        )
        per_lot = default_commission_per_lot(asset)
        grid[asset] = {}
        if df is None or len(df) == 0:
            for st in strats:
                grid[asset][st] = {"error": "no data"}
            continue
        for st in strats:
            res = run_backtest(df, build_strategy(st), asset, req.initial_capital,
                               commission_per_lot=per_lot, timeframe=req.timeframe)
            m = res.metrics
            grid[asset][st] = {
                "return_pct": m["total_return_pct"],
                "win_rate_pct": m["win_rate_pct"],
                "profit_factor": m["profit_factor"],
                "max_dd_pct": m["max_drawdown_pct"],
                "trades": m["total_trades"],
            }
    return {"assets": assets, "strategies": strats, "grid": grid}


class BacktestRequest(BaseModel):
    asset: str = "GOLD"
    timeframe: str = "H1"
    strategy: str = "sma_crossover"
    count: int = 3000
    initial_capital: float = 1000.0
    # Per-strategy overrides (EMAs, SL/TP pips, periods…). Keys the chosen
    # strategy doesn't accept are ignored; omitted → strategy defaults.
    strategy_params: dict | None = None
    spread: float = 0.0
    # Brokerage. per-lot is the Vantage-accurate model (per lot per side); leave
    # it null to auto-fill the asset's reference rate from constants.
    commission_per_lot: float | None = None
    commission_pct: float = 0.0
    commission_per_trade: float = 0.0
    walk_forward: bool = True
    source: str = "mt5"  # "mt5" (live) | "imported" (AlphaEdge CSV copy)


@router.post("/run")
def run(req: BacktestRequest) -> dict:
    df = _completed_bars(
        market_data.get_ohlcv(req.asset, req.timeframe, req.count, req.source), req.source,
    )
    if df is None or len(df) == 0:
        msg = ("No imported data — run 'Import from AlphaEdge' first."
               if req.source == "imported"
               else "No market data (MT5 not connected / stub mode).")
        return {"error": msg}
    strategy = build_strategy(req.strategy, req.strategy_params)
    per_lot = (req.commission_per_lot if req.commission_per_lot is not None
               else default_commission_per_lot(req.asset))
    result = run_backtest(
        df, strategy, req.asset, req.initial_capital, spread=req.spread,
        commission_pct=req.commission_pct, commission_per_trade=req.commission_per_trade,
        commission_per_lot=per_lot, timeframe=req.timeframe,
    )
    payload = {"metrics": result.metrics, "trades": result.trades[-50:],
               "equity_curve": result.equity_curve,
               "commission_per_lot_used": per_lot}
    if req.walk_forward:
        payload["walk_forward"] = walk_forward(
            df, strategy, req.asset, initial_capital=req.initial_capital,
            spread=req.spread, commission_pct=req.commission_pct,
            commission_per_trade=req.commission_per_trade, commission_per_lot=per_lot,
            timeframe=req.timeframe,
        )
    return payload
