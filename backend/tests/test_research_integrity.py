import tempfile
from pathlib import Path
from unittest import TestCase
import pandas as pd
from research_continuation import resolve_exit, validate_bars, simulate
from research_dataset import freeze, load_snapshot, forward_subset
from app.pipeline.context import Signal, Direction


def bars():
    return pd.DataFrame({'open':[100.,100.,100.], 'high':[101.,105.,101.],
                         'low':[99.,95.,99.], 'close':[100.,100.,100.]},
                        index=pd.date_range('2026-01-01',periods=3,freq='30min'))


class ResearchIntegrityTests(TestCase):
    def test_gap_order_and_ambiguous_bars(self):
        self.assertEqual(resolve_exit(1,90,110,115,120,80,1),(110,'gap_target'))
        self.assertEqual(resolve_exit(-1,110,90,85,120,80,1),(90,'gap_target'))
        self.assertEqual(resolve_exit(1,90,110,85,115,80,1),(84,'gap_stop'))
        self.assertEqual(resolve_exit(1,90,110,100,115,85,1),(89,'stop'))
        self.assertEqual(resolve_exit(-1,110,90,100,115,85,1),(111,'stop'))

    def test_bad_bars_rejected(self):
        df = bars()
        df.loc[df.index[1],'high'] = 80
        with self.assertRaises(ValueError):
            validate_bars(df)
        df = bars()
        df.index = [df.index[0]] * 3
        with self.assertRaises(ValueError):
            validate_bars(df)

    def test_next_bar_execution_and_ledger(self):
        df = bars()
        spec = dict(ask=100.2,bid=100.,point=.01,trade_tick_value_loss=1.,
                    trade_tick_size=1.,volume_step=.01,volume_min=.01,volume_max=100.)
        signals = [Signal('BTC',Direction.BUY,100,98,104),None,None]
        result = simulate(df,signals,spec,'BTC',0,3,1)
        trade = result['ledger'][0]
        self.assertEqual(trade['entry_time'],str(df.index[1]))
        self.assertEqual(trade['signal_time'],str(df.index[0]))
        self.assertEqual(trade['reason'],'stop')
        self.assertLess(trade['net_pnl'],0)

    def test_snapshot_tampering_and_no_overlap(self):
        with tempfile.TemporaryDirectory() as root:
            dest = Path(root)/'snapshot'
            frames = {'GOLD':bars(),'BTC':bars()}
            manifest = freeze(dest,frames,{'GOLD':{},'BTC':{}},'2026-01-01T02:00:00Z')
            _, loaded = load_snapshot(dest)
            self.assertEqual(len(loaded['GOLD']),3)
            boundary = manifest['assets']['GOLD']['forward_from_broker_time']
            self.assertTrue(forward_subset(bars(),boundary).empty)
            with self.assertRaises(FileExistsError):
                freeze(dest,frames,{},'later')
            with (dest/'GOLD.csv').open('a') as stream:
                stream.write('\n')
            with self.assertRaises(ValueError):
                load_snapshot(dest)
