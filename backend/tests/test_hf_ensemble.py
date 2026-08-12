from __future__ import annotations

import unittest

from app.ai_engine.hf_ensemble import _combine_signals, _for_trade_direction


class DirectionMappingTests(unittest.TestCase):
    def test_bullish_forecast_supports_buy(self):
        self.assertAlmostEqual(_for_trade_direction(0.75, "BUY"), 0.75)

    def test_bearish_forecast_supports_sell(self):
        self.assertAlmostEqual(_for_trade_direction(0.25, "SELL"), 0.75)


class AvailableWeightTests(unittest.TestCase):
    def test_missing_models_do_not_dilute_foundation(self):
        score, _, agreement, _, weights = _combine_signals({
            "direct": (0.5, 1.0, False),
            "foundation": (0.70, 0.60, True),
            "sentiment": (0.5, 1.0, False),
        })
        self.assertEqual(weights, {"foundation": 1.0})
        self.assertEqual(agreement, 1.0)
        self.assertGreater(score, 0.60)

    def test_available_weights_are_renormalized(self):
        _, _, _, _, weights = _combine_signals({
            "direct": (0.65, 0.25, True),
            "foundation": (0.60, 0.40, True),
            "sentiment": (0.5, 1.0, False),
        })
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertAlmostEqual(weights["direct"], 0.45 / 0.80)
        self.assertAlmostEqual(weights["foundation"], 0.35 / 0.80)

    def test_disagreement_reduces_confidence(self):
        agreeing = _combine_signals({
            "direct": (0.70, 0.20, True),
            "foundation": (0.70, 0.20, True),
            "sentiment": (0.5, 1.0, False),
        })[0]
        conflicting = _combine_signals({
            "direct": (0.70, 0.20, True),
            "foundation": (0.30, 0.20, True),
            "sentiment": (0.5, 1.0, False),
        })[0]
        self.assertGreater(agreeing, conflicting)


if __name__ == "__main__":
    unittest.main()
