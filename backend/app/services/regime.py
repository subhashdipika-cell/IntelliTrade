"""Market-regime classifier.

Labels a slice of OHLCV with a trend/volatility regime so trades and backtests
can be grouped by 'which regime were we in' — the basis for 'which strategy works
in which market'. Returns a human label plus the numeric features behind it:
  • trend strength : ADX(14)
  • trend direction: EMA50 vs EMA200 + EMA50 slope over the last 20 bars
  • volatility     : ATR(14) as % of price, ranked against the trailing window

Label form: "<Uptrend|Downtrend|Range> / <Low|Normal|High>-vol".
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.strategies import indicators as ind

_ADX_RANGE_THRESHOLD = 20.0   # below this ADX, treat as a non-trending range
_SLOPE_BARS = 20


def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat([(high - low),
                    (high - close.shift()).abs(),
                    (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.rolling(period).mean()


def classify(df: pd.DataFrame) -> dict:
    """Classify the regime at the LAST bar of df. Safe on short/empty frames."""
    unknown = {"label": "Unknown", "trend": "Unknown", "volatility": "Unknown",
               "adx": None, "atr_pct": None, "ema_slope_pct": None}
    if df is None or len(df) < 60:
        return unknown

    close = df["close"]
    price = float(close.iloc[-1])
    if price == 0 or np.isnan(price):
        return unknown

    ema50 = ind.ema(close, 50)
    ema200 = ind.ema(close, 200) if len(df) >= 200 else ind.ema(close, min(len(df) - 1, 100))
    atr = ind.atr(df, 14)
    adx = _adx(df, 14)

    adx_v = float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 0.0
    atr_pct = float(atr.iloc[-1]) / price * 100 if not np.isnan(atr.iloc[-1]) else None

    # trend direction from the 50/200 relationship + recent EMA50 slope
    slope_ref = ema50.iloc[-1 - _SLOPE_BARS] if len(ema50) > _SLOPE_BARS else ema50.iloc[0]
    ema_slope_pct = ((ema50.iloc[-1] - slope_ref) / slope_ref * 100
                     if slope_ref else 0.0)
    up = ema50.iloc[-1] > ema200.iloc[-1]

    if adx_v < _ADX_RANGE_THRESHOLD:
        trend = "Range"
    elif up:
        trend = "Uptrend"
    else:
        trend = "Downtrend"

    # volatility bucket: rank current ATR% against its trailing distribution
    atr_pct_series = (atr / close * 100).dropna()
    window = atr_pct_series.tail(200)
    if atr_pct is None or len(window) < 20:
        vol = "Normal"
    else:
        rank = (window < atr_pct).mean()  # 0..1 percentile of current vs window
        vol = "Low" if rank < 0.33 else ("High" if rank > 0.66 else "Normal")

    return {
        "label": f"{trend} / {vol}-vol",
        "trend": trend,
        "volatility": vol,
        "adx": round(adx_v, 1),
        "atr_pct": round(atr_pct, 3) if atr_pct is not None else None,
        "ema_slope_pct": round(float(ema_slope_pct), 3),
    }
