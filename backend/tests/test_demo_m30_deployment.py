from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from app.pipeline.context import Direction, Signal, TradeContext, Verdict
from app.pipeline.stages.risk import RiskConfig, RiskStage
from app.backtest.walk_forward import walk_forward
from app.api.routes.backtest import _completed_bars
from app.strategies.demo_m30_trend import BtcM30Trend, GoldM30Trend
from app.strategies.registry import strategy_scan_lookback, strategy_scan_timeframe


def _frame() -> pd.DataFrame:
    close = np.linspace(2000, 2200, 220)
    return pd.DataFrame({
        "open": close - 0.2, "high": close + 1, "low": close - 1,
        "close": close, "tick_volume": np.full(len(close), 100),
    }, index=pd.date_range("2026-01-01", periods=len(close), freq="30min"))


class DemoM30DeploymentTests(unittest.TestCase):
    def test_specialized_strategies_are_asset_and_m30_scoped(self):
        frame = _frame()
        self.assertEqual(strategy_scan_timeframe("gold_m30_trend"), "M30")
        self.assertEqual(strategy_scan_lookback("btc_m30_trend"), 500)
        self.assertEqual((GoldM30Trend().fast, GoldM30Trend().slow), (50, 100))
        self.assertEqual((BtcM30Trend().fast, BtcM30Trend().slow), (60, 100))
        self.assertTrue(all(x is None for x in GoldM30Trend().signals("BTC", frame, "M30")))
        self.assertTrue(all(x is None for x in BtcM30Trend().signals("BTC", frame, "H1")))

    def test_risk_stage_sizes_from_stop_and_equity_below_configured_cap(self):
        sig = Signal("BTC", Direction.BUY, 100.0, 90.0, 122.0, "M30")
        ctx = TradeContext("BTC", "M30", signal=sig)
        cfg = RiskConfig(
            lots_by_asset={"BTC": 0.2}, risk_per_trade_pct=0.5,
            profit_lock_enabled=False,
        )
        spec = {
            "point": 0.01, "trade_tick_size": 0.01, "trade_tick_value_loss": 0.01,
            "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01,
            "ask": 100.0, "bid": 99.9,
        }
        with (
            patch("app.pipeline.stages.risk.mt5_client.account_info", return_value={"equity": 1000.0}),
            patch("app.pipeline.stages.risk.mt5_client.symbol_spec", return_value=spec),
            patch("app.pipeline.stages.risk.mt5_client.calc_margin", return_value=2.0),
            patch("app.pipeline.stages.risk.gold_hours.is_gold", return_value=False),
        ):
            RiskStage(cfg).process(ctx)
        self.assertIs(ctx.decisions[-1].verdict, Verdict.PASS)
        self.assertEqual(ctx.signal.lots, 0.2)

    def test_risk_stage_refuses_when_broker_minimum_exceeds_budget(self):
        sig = Signal("BTC", Direction.BUY, 100.0, 0.0, 320.0, "M30")
        ctx = TradeContext("BTC", "M30", signal=sig)
        cfg = RiskConfig(
            lots_by_asset={"BTC": 0.2}, risk_per_trade_pct=0.5,
            profit_lock_enabled=False,
        )
        spec = {
            "point": 0.01, "trade_tick_size": 0.01, "trade_tick_value_loss": 0.01,
            "volume_min": 0.1, "volume_max": 100.0, "volume_step": 0.1,
            "ask": 100.0, "bid": 99.9,
        }
        with (
            patch("app.pipeline.stages.risk.mt5_client.account_info", return_value={"equity": 1000.0}),
            patch("app.pipeline.stages.risk.mt5_client.symbol_spec", return_value=spec),
            patch("app.pipeline.stages.risk.gold_hours.is_gold", return_value=False),
        ):
            RiskStage(cfg).process(ctx)
        self.assertIs(ctx.decisions[-1].verdict, Verdict.BLOCK)
        self.assertIn("order refused", ctx.decisions[-1].reason)

    def test_walk_forward_preserves_strategy_timeframe(self):
        frame = _frame()
        with patch("app.backtest.walk_forward.run_backtest") as run:
            run.return_value.metrics = {"total_return_pct": 0.0}
            walk_forward(frame, GoldM30Trend(), "GOLD", n_folds=2, timeframe="M30")
        self.assertTrue(run.called)
        self.assertTrue(all(call.kwargs["timeframe"] == "M30" for call in run.call_args_list))

    def test_mt5_backtest_drops_forming_candle(self):
        frame = _frame()
        self.assertEqual(len(_completed_bars(frame, "mt5")), len(frame) - 1)
        self.assertEqual(len(_completed_bars(frame, "imported")), len(frame))


if __name__ == "__main__":
    unittest.main()
