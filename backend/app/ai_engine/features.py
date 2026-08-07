"""Feature engineering shared by training and evaluation. The SAME columns must
be produced in both places, so they live here as FEATURE_COLS."""
from __future__ import annotations

import numpy as np
import pandas as pd

MARKET_FEATURE_COLS = ["returns", "rsi", "macd_norm", "atr_pct", "mom_10"]
CONTEXT_FEATURE_COLS = ["direction_buy", "planned_rr", "strategy_bucket", "timeframe_code"]
FEATURE_COLS = MARKET_FEATURE_COLS + CONTEXT_FEATURE_COLS


def context_features(direction: str = "BUY", planned_rr: float = 0.0,
                     strategy: str | None = None, timeframe: str = "H1") -> dict[str, float]:
    """Stable non-market features shared by training and live scoring."""
    import hashlib
    key = (strategy or "unknown").strip().lower().encode("utf-8")
    bucket = int.from_bytes(hashlib.sha256(key).digest()[:2], "big") % 32
    tf_code = {"M1": 1, "M5": 5, "M15": 15, "M30": 30,
               "H1": 60, "H4": 240, "D1": 1440}.get(timeframe.upper(), 60)
    return {"direction_buy": 1.0 if direction.upper() == "BUY" else 0.0,
            "planned_rr": float(planned_rr or 0.0),
            "strategy_bucket": float(bucket), "timeframe_code": float(tf_code)}


def generate_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["returns"] = df["close"].pct_change()
    df["rsi"] = _rsi(df["close"], 14)

    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    # normalise MACD by price so it's comparable across assets (Gold vs BTC)
    df["macd_norm"] = (ema12 - ema26) / df["close"]

    df["atr_pct"] = _atr(df, 14) / df["close"]
    df["mom_10"] = df["close"] / df["close"].shift(10) - 1
    return df


def _rsi(prices: pd.Series, period: int) -> pd.Series:
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()
