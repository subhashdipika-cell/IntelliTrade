from unittest import TestCase
from unittest.mock import patch
from app.pipeline.context import TradeContext, Signal, Direction
from app.pipeline.stages.strategy import StrategyStage
from app.strategies.demo_m30_trend import GoldM30Trend


class TrendPolicyTests(TestCase):
    def test_fixed_bracket_is_demo_only(self):
        for mode in ('DEMO', 'LIVE', None):
            strategy = GoldM30Trend()
            ctx = TradeContext('GOLD', 'M30')
            stage = StrategyStage(strategy)
            with patch.object(strategy, 'generate', return_value=Signal('GOLD', Direction.BUY, 100, 90, 122)), patch('app.services.mt5_client.mt5_client.verify_account_type', return_value=mode), patch.object(stage, '_cap_target_to_structure') as cap, patch.object(stage, '_human_touch') as levels:
                stage.process(ctx)
            self.assertEqual(ctx.blocked, mode != 'DEMO')
            self.assertEqual(ctx.signal.target, 122)
            cap.assert_not_called()
            levels.assert_not_called()
