"""Strategy registry. Concrete classes registered here are selectable from the
Backtest and Live pages. Adding a strategy = implement Strategy + register it;
no core changes. (This is the pragmatic version of a plugin system — a registry,
introduced now that there are two strategies and the seam is real.)"""
from __future__ import annotations

from app.strategies.base import Strategy
from app.strategies.bollinger_reversion import BollingerReversion
from app.strategies.break_retest import BreakRetest
from app.strategies.donchian_breakout import DonchianBreakout
from app.strategies.ema_pullback import EmaPullback
from app.strategies.ema_pullback_scalp import EmaPullbackScalp
from app.strategies.gold_m5_pullback import GoldM5Pullback
from app.strategies.macd_cross import MacdCross
from app.strategies.rsi_reversion import RsiReversion
from app.strategies.sma_crossover import SmaCrossover

_REGISTRY: dict[str, type[Strategy]] = {
    "sma_crossover": SmaCrossover,
    "donchian_breakout": DonchianBreakout,
    "break_retest": BreakRetest,
    "ema_pullback": EmaPullback,
    "ema_pullback_scalp": EmaPullbackScalp,
    "macd_cross": MacdCross,
    "rsi_reversion": RsiReversion,
    "bollinger_reversion": BollingerReversion,
    "gold_m5_pullback": GoldM5Pullback,
}


def list_strategies() -> list[str]:
    return list(_REGISTRY)


def strategy_scan_timeframe(name: str) -> str | None:
    """A strategy's own scan timeframe (e.g. 'M5') if it declares one, else None
    — lets the scanner run this strategy on a different timeframe than the
    global one (class attribute, read without instantiating)."""
    cls = _REGISTRY.get(name)
    return getattr(cls, "scan_timeframe", None) if cls else None


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
