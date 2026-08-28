"""Strategy registry. Concrete classes registered here are selectable from the
Backtest and Live pages. Adding a strategy = implement Strategy + register it;
no core changes. (This is the pragmatic version of a plugin system — a registry,
introduced now that there are two strategies and the seam is real.)"""
from __future__ import annotations

from app.strategies.base import Strategy
from app.strategies.bollinger_reversion import BollingerReversion
from app.strategies.break_retest import BreakRetest
from app.strategies.donchian_breakout import DonchianBreakout
from app.strategies.eighty_twenty import EightyTwenty
from app.strategies.ema_pullback import EmaPullback
from app.strategies.ema_pullback_scalp import EmaPullbackScalp
from app.strategies.ema_atr_adx_trend import EmaAtrAdxTrend
from app.strategies.gold_m5_pullback import GoldM5Pullback
from app.strategies.gold_h1_ema_atr_adx import GoldH1EmaAtrAdx
from app.strategies.macd_cross import MacdCross
from app.strategies.momentum_pinball import MomentumPinball
from app.strategies.price_action_scalp import PriceActionScalp
from app.strategies.gold_macd_trend import GoldMacdTrend
from app.strategies.gold_session_break_retest import GoldSessionBreakRetest
from app.strategies.range_reversion_scalp import RangeReversionScalp
from app.strategies.hybrid_gold_m1_scalp import HybridGoldM1Scalp
from app.strategies.smc_confluence import SmcConfluence
from app.strategies.rsi_reversion import RsiReversion
from app.strategies.sma_crossover import SmaCrossover
from app.strategies.turtle_soup import TurtleSoup
from app.strategies.btc_volatility_break_retest import BtcVolatilityBreakRetest

_REGISTRY: dict[str, type[Strategy]] = {
    "sma_crossover": SmaCrossover,
    "donchian_breakout": DonchianBreakout,
    "break_retest": BreakRetest,
    "ema_pullback": EmaPullback,
    "ema_pullback_scalp": EmaPullbackScalp,
    "ema_atr_adx_trend": EmaAtrAdxTrend,
    "macd_cross": MacdCross,
    "rsi_reversion": RsiReversion,
    "bollinger_reversion": BollingerReversion,
    "gold_m5_pullback": GoldM5Pullback,
    "gold_h1_ema_atr_adx": GoldH1EmaAtrAdx,
    "price_action_scalp": PriceActionScalp,
    "smt_gold_macd_trend": GoldMacdTrend,
    "gold_session_break_retest": GoldSessionBreakRetest,
    "range_reversion_scalp": RangeReversionScalp,
    "hybrid_gold_m1_scalp": HybridGoldM1Scalp,
    "smc_confluence": SmcConfluence,
    "btc_volatility_break_retest": BtcVolatilityBreakRetest,
    # Street Smarts (Connors & Raschke) swing patterns — H4 by default.
    # Registered = selectable for backtest/live; deploying them live still
    # requires adding them to the scanner's per-asset strategy settings.
    "turtle_soup": TurtleSoup,
    "eighty_twenty": EightyTwenty,
    "momentum_pinball": MomentumPinball,
}


def list_strategies() -> list[str]:
    return list(_REGISTRY)


def strategy_scan_timeframe(name: str) -> str | None:
    """A strategy's own scan timeframe (e.g. 'M5') if it declares one, else None
    — lets the scanner run this strategy on a different timeframe than the
    global one (class attribute, read without instantiating)."""
    cls = _REGISTRY.get(name)
    return getattr(cls, "scan_timeframe", None) if cls else None


def strategy_scan_lookback(name: str) -> int:
    """Number of closed bars needed by the live scanner for a strategy."""
    cls = _REGISTRY.get(name)
    return int(getattr(cls, "scan_lookback", 500) if cls else 500)


def build_strategy(name: str, params: dict | None = None) -> Strategy:
    cls = _REGISTRY.get(name, SmaCrossover)
    if not params:
        return cls()
    # Keep only keys this strategy's constructor accepts (callers may pass a
    # superset, e.g. a backtest form), and coerce to the annotated type so a JSON
    # float like 9.0 doesn't break an int window.
    import inspect

    sig = inspect.signature(cls)
    filtered: dict = {}
    for key, val in params.items():
        if key not in sig.parameters or val is None:
            continue
        # `from __future__ import annotations` makes annotations strings, so match
        # by name to coerce a JSON float like 9.0 to the int a rolling window needs.
        ann = sig.parameters[key].annotation
        ann_name = ann if isinstance(ann, str) else getattr(ann, "__name__", "")
        try:
            if ann_name == "int":
                val = int(val)
            elif ann_name == "float":
                val = float(val)
        except (TypeError, ValueError):
            pass
        filtered[key] = val
    try:
        return cls(**filtered)
    except TypeError:
        return cls()
