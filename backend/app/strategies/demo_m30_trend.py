"""Asset-specific M30 trend strategies selected from DEMO broker data.

These deliberately use fixed, research-selected parameters so Money-Mgmt's
global RR setting cannot silently change the live rule after validation.
"""
from __future__ import annotations

import pandas as pd

from app.pipeline.context import Signal
from app.strategies.sma_crossover import SmaCrossover


class _ScopedM30Sma(SmaCrossover):
    scan_timeframe = "M30"
    scan_lookback = 500
    allowed_asset = ""

    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        if asset != self.allowed_asset or timeframe != self.scan_timeframe:
            return None
        return super().generate(asset, df, timeframe)

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        if df is None:
            return []
        if asset != self.allowed_asset or timeframe != self.scan_timeframe:
            return [None] * len(df)
        return super().signals(asset, df, timeframe)


class GoldM30Trend(_ScopedM30Sma):
    """Gold M30 SMA(50/100), 1.5 ATR stop and 2.2R fixed target."""

    name = "Gold M30 Trend"
    allowed_asset = "GOLD"

    def __init__(self) -> None:
        super().__init__(fast=50, slow=100, atr_period=14, sl_atr=1.5, rr=2.2)


class BtcM30Trend(_ScopedM30Sma):
    """BTC M30 SMA(60/100), 1.2 ATR stop and 2.2R fixed target."""

    name = "BTC M30 Trend"
    allowed_asset = "BTC"

    def __init__(self) -> None:
        super().__init__(fast=60, slow=100, atr_period=14, sl_atr=1.2, rr=2.2)
