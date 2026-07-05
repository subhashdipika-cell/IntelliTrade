"""Shared indicator helpers so strategies don't each reimplement them."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def rsi(s: pd.Series, period: int = 14) -> pd.Series:
    d = s.diff()
    gain = d.where(d > 0, 0.0).rolling(period).mean()
    loss = (-d.where(d < 0, 0.0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def macd(s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(s, fast) - ema(s, slow)
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig


def bollinger(s: pd.Series, period: int = 20, k: float = 2.0):
    mid = s.rolling(period).mean()
    sd = s.rolling(period).std()
    return mid, mid + k * sd, mid - k * sd


def bracket(direction: str, price: float, a: float, sl_atr: float, rr: float):
    """ATR-based stop/target. Returns (sl, tp) rounded."""
    if direction == "BUY":
        return round(price - sl_atr * a, 5), round(price + sl_atr * a * rr, 5)
    return round(price + sl_atr * a, 5), round(price - sl_atr * a * rr, 5)


def swing_levels(df: pd.DataFrame, lookback: int = 20) -> tuple[float, float]:
    """Nearest swing resistance / support over the last `lookback` CLOSED bars,
    excluding the most recent (forming/breakout) bar so a breakout isn't capped
    by its own bar. Returns (resistance, support)."""
    window = df.iloc[-(lookback + 1):-1] if len(df) > lookback + 1 else df.iloc[:-1]
    if window.empty:
        window = df
    return float(window["high"].max()), float(window["low"].min())


def cap_target_to_structure(
    direction: str, entry: float, sl: float, tp: float, df: pd.DataFrame,
    a: float, lookback: int = 20, buffer_atr: float = 0.25,
) -> tuple[float, float | None, float]:
    """Pull the target back to just inside the nearest swing level when that level
    sits between entry and the original target (i.e. the target aims past a wall).

    Returns (capped_tp, resistance_or_support_used | None, rr_after).
    For a breakout entering at a fresh extreme there is no level beyond entry in
    the window, so the target is left unchanged.
    """
    res, sup = swing_levels(df, lookback)
    buf = buffer_atr * a
    risk = abs(entry - sl)
    new_tp, level = tp, None

    if direction == "BUY":
        # Resistance must be above entry and tighter than the current target.
        if res > entry and (res - buf) < tp:
            new_tp, level = max(entry, round(res - buf, 5)), res
    else:
        if sup < entry and (sup + buf) > tp:
            new_tp, level = min(entry, round(sup + buf, 5)), sup

    rr_after = abs(new_tp - entry) / risk if risk > 0 else 0.0
    return new_tp, level, rr_after
