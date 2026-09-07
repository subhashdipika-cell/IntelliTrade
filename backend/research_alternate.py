"""Run the fixed alternate families through the same evaluation as continuation."""
from research_continuation import main
from app.strategies.alternate_research import GoldRangeReversal, BtcSqueezeBreakout
from app.strategies.demo_m30_trend import GoldM30Trend, BtcM30Trend

if __name__ == '__main__':
    main([('GOLD',GoldRangeReversal(),GoldM30Trend()),
          ('BTC',BtcSqueezeBreakout(),BtcM30Trend())],
         'alternate_research_2026-09-07.json')
