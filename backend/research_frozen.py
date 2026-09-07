"""Reproduce the alternate comparison from a verified local snapshot, offline."""
import argparse
from research_continuation import main
from app.strategies.alternate_research import GoldRangeReversal, BtcSqueezeBreakout
from app.strategies.demo_m30_trend import GoldM30Trend, BtcM30Trend

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('snapshot')
    parser.add_argument('--report', default='frozen_research_v2_2026-09-07.json')
    args = parser.parse_args()
    main([('GOLD',GoldRangeReversal(),GoldM30Trend()),
          ('BTC',BtcSqueezeBreakout(),BtcM30Trend())],args.report,args.snapshot)
