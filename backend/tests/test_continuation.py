from unittest import TestCase
from unittest.mock import patch
import numpy as np
import pandas as pd
from app.strategies.continuation_research import GoldContinuation, BtcContinuation
from app.strategies.alternate_research import GoldRangeReversal, BtcSqueezeBreakout
from app.pipeline.context import TradeContext
from app.pipeline.stages.strategy import StrategyStage


class ContinuationTests(TestCase):
    def test_causal_window_parity_and_asset_scope(self):
        rng = np.random.default_rng(42)
        close = 2000 + np.cumsum(rng.normal(.1, 2, 800))
        df = pd.DataFrame(dict(open=close-.2, high=close+1, low=close-1,
                               close=close, tick_volume=rng.integers(20,200,800)),
                          index=pd.date_range('2025-01-01',periods=800,freq='30min'))
        for strategy in [GoldContinuation(), BtcContinuation(), GoldRangeReversal(), BtcSqueezeBreakout()]:
            full = strategy.signals(strategy.asset,df,'M30')
            for i in range(500,800,7):
                self.assertEqual(full[i],strategy.generate(strategy.asset,df.iloc[i-498:i+1],'M30'))
            self.assertTrue(all(s is None for s in strategy.signals('ETH',df,'M30')))
            self.assertIsNone(strategy.generate(strategy.asset,df,'M5'))

    def test_research_candidate_cannot_execute(self):
        for strategy in [GoldContinuation(), BtcContinuation(), GoldRangeReversal(), BtcSqueezeBreakout()]:
            with patch.object(strategy,'generate') as generate:
                ctx = StrategyStage(strategy).process(TradeContext(strategy.asset,'M30'))
            self.assertTrue(ctx.blocked)
            generate.assert_not_called()
