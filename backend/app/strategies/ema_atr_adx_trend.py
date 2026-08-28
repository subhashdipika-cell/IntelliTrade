"""Completed-candle port of the Pine ``EMA ATR ADX Trend Signals`` indicator.

The Pine source draws TP1 and TP2 but does not define partial exits. IntelliTrade
supports one executable target, so ``target_rr`` is explicit and defaults to the
Pine TP2 value (2.5R). Set it to 1.5 to backtest the TP1 variant.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal
from app.strategies.base import Strategy


class EmaAtrAdxTrend(Strategy):
    name = "EMA ATR ADX Trend"
    scan_lookback = 500

    def __init__(
        self,
        fast_ema_length: int = 9,
        slow_ema_length: int = 21,
        atr_length: int = 14,
        atr_multiplier: float = 1.5,
        sl_atr_multiple: float = 1.5,
        target_rr: float = 2.5,
        adx_length: int = 14,
        adx_smoothing: int = 14,
        adx_threshold: float = 20.0,
        use_high_volume_buy: bool = True,
        volume_length: int = 20,
        volume_multiplier: float = 1.5,
    ) -> None:
        self.fast_ema_length = max(1, int(fast_ema_length))
        self.slow_ema_length = max(2, int(slow_ema_length))
        self.atr_length = max(1, int(atr_length))
        self.atr_multiplier = max(0.1, float(atr_multiplier))
        self.sl_atr_multiple = max(0.1, float(sl_atr_multiple))
        self.target_rr = max(0.1, float(target_rr))
        self.adx_length = max(1, int(adx_length))
        self.adx_smoothing = max(1, int(adx_smoothing))
        self.adx_threshold = max(0.0, float(adx_threshold))
        self.use_high_volume_buy = bool(use_high_volume_buy)
        self.volume_length = max(1, int(volume_length))
        self.volume_multiplier = max(0.1, float(volume_multiplier))

    @staticmethod
    def _rma(values: np.ndarray, length: int) -> np.ndarray:
        """Causal Wilder moving average, matching Pine ``ta.rma`` seeding."""
        values = np.asarray(values, dtype=float)
        out = np.full(len(values), np.nan, dtype=float)
        seed: list[float] = []
        previous = np.nan
        alpha = 1.0 / length
        for i, value in enumerate(values):
            if not np.isfinite(value):
                continue
            if not np.isfinite(previous):
                seed.append(float(value))
                if len(seed) < length:
                    continue
                previous = float(np.mean(seed[-length:]))
            else:
                previous = alpha * float(value) + (1.0 - alpha) * previous
            out[i] = previous
        return out

    def _series(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        close = df["close"].to_numpy(dtype=float)
        high = df["high"].to_numpy(dtype=float)
        low = df["low"].to_numpy(dtype=float)
        open_ = df["open"].to_numpy(dtype=float)
        volume_col = "volume" if "volume" in df.columns else "tick_volume"
        volume = (df[volume_col].to_numpy(dtype=float)
                  if volume_col in df.columns else np.full(len(df), np.nan))

        fast = pd.Series(close).ewm(
            span=self.fast_ema_length, adjust=False
        ).mean().to_numpy()
        slow = pd.Series(close).ewm(
            span=self.slow_ema_length, adjust=False
        ).mean().to_numpy()

        prior_close = np.roll(close, 1)
        prior_close[0] = close[0]
        true_range = np.maximum.reduce([
            high - low,
            np.abs(high - prior_close),
            np.abs(low - prior_close),
        ])
        atr = self._rma(true_range, self.atr_length)

        up = np.diff(high, prepend=np.nan)
        down = -np.diff(low, prepend=np.nan)
        plus_dm = np.where((up > down) & (up > 0), up, 0.0)
        minus_dm = np.where((down > up) & (down > 0), down, 0.0)
        plus_dm[0] = minus_dm[0] = np.nan
        smoothed_tr = self._rma(true_range, self.adx_length)
        plus_di = 100.0 * self._rma(plus_dm, self.adx_length) / smoothed_tr
        minus_di = 100.0 * self._rma(minus_dm, self.adx_length) / smoothed_tr
        di_sum = plus_di + minus_di
        dx = np.full(len(df), np.nan, dtype=float)
        valid_di = np.isfinite(plus_di) & np.isfinite(minus_di)
        dx[valid_di & (di_sum == 0)] = 0.0
        directional = valid_di & (di_sum > 0)
        dx[directional] = (
            100.0 * np.abs(plus_di[directional] - minus_di[directional])
            / di_sum[directional]
        )
        adx = self._rma(dx, self.adx_smoothing)

        volume_average = pd.Series(volume).rolling(self.volume_length).mean().to_numpy()
        return {
            "open": open_, "close": close, "fast": fast, "slow": slow,
            "atr": atr, "adx": adx, "volume": volume,
            "volume_average": volume_average,
        }

    def _scan(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        n = 0 if df is None else len(df)
        out: list[Signal | None] = [None] * n
        if n == 0:
            self.last_reason = "Insufficient history: no completed bars."
            return out

        s = self._series(df)
        active_trend = 0
        signal_issued_in_trend = False
        last_reason = "No confirmed EMA/ATR/ADX setup on the latest closed bar."

        for i in range(n):
            fast, slow = s["fast"][i], s["slow"][i]
            atr, adx = s["atr"][i], s["adx"][i]
            if not all(np.isfinite(v) for v in (fast, slow, atr, adx)) or atr <= 0:
                last_reason = "Indicators warming up: EMA, ATR, or ADX unavailable."
                continue

            bullish = fast > slow
            bearish = fast < slow
            if bullish and active_trend != 1:
                active_trend = 1
                signal_issued_in_trend = False
            elif bearish and active_trend != -1:
                active_trend = -1
                signal_issued_in_trend = False

            close = float(s["close"][i])
            upper = slow + atr * self.atr_multiplier
            lower = slow - atr * self.atr_multiplier
            bullish_breakout = close > upper
            bearish_breakout = close < lower
            strong_trend = adx > self.adx_threshold

            volume = s["volume"][i]
            volume_average = s["volume_average"][i]
            high_volume_bullish = (
                np.isfinite(volume) and np.isfinite(volume_average)
                and volume > volume_average * self.volume_multiplier
                and close > float(s["open"][i])
            )
            buy_confirmed = bullish_breakout or (
                self.use_high_volume_buy and high_volume_bullish
            )

            if signal_issued_in_trend:
                last_reason = "Trend-cycle filter: a signal was already issued in this EMA trend."
                continue
            if not strong_trend:
                last_reason = f"ADX filter: {adx:.2f} is not above {self.adx_threshold:.2f}."
                continue

            risk = atr * self.sl_atr_multiple
            if bullish and buy_confirmed:
                out[i] = Signal(
                    asset, Direction.BUY, close, round(close - risk, 5),
                    round(close + risk * self.target_rr, 5), timeframe,
                )
                signal_issued_in_trend = True
                last_reason = "Signal confirmed: bullish EMA trend with volatility confirmation."
            elif bearish and bearish_breakout:
                out[i] = Signal(
                    asset, Direction.SELL, close, round(close + risk, 5),
                    round(close - risk * self.target_rr, 5), timeframe,
                )
                signal_issued_in_trend = True
                last_reason = "Signal confirmed: bearish EMA trend with ATR breakout."
            elif bullish:
                last_reason = "Volatility filter: no bullish ATR breakout or high-volume bullish candle."
            elif bearish:
                last_reason = "Volatility filter: no bearish ATR breakout."
            else:
                last_reason = "EMA filter: fast and slow EMA are equal."

        self.last_reason = last_reason
        return out

    def generate(self, asset: str, df: pd.DataFrame, timeframe: str) -> Signal | None:
        signals = self._scan(asset, df, timeframe)
        return signals[-1] if signals else None

    def signals(self, asset: str, df: pd.DataFrame, timeframe: str) -> list[Signal | None]:
        return self._scan(asset, df, timeframe)
