from __future__ import annotations

from datetime import datetime, timezone
import os
import tempfile
import unittest

from app.services.scanner_decision_store import ScannerDecisionStore


class ScannerDecisionStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ScannerDecisionStore(
            os.path.join(self.tmp.name, "decisions.jsonl"), max_records=3
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_recent_filters_and_retains_tail(self):
        for i in range(4):
            self.store.append({
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
                "asset": "GOLD" if i % 2 else "BTC",
                "strategy": "Price Action Scalp", "status": "blocked",
                "blocked_by": "strategy", "n": i,
            })
        self.assertEqual([r["n"] for r in self.store.recent(10)], [3, 2, 1])
        self.assertEqual(len(self.store.recent(10, asset="GOLD")), 2)

    def test_blocker_summary(self):
        now = datetime.now(timezone.utc).isoformat()
        self.store.append({"evaluated_at": now, "status": "blocked",
                           "blocked_by": "strategy", "strategy": "A"})
        self.store.append({"evaluated_at": now, "status": "executed",
                           "blocked_by": None, "strategy": "A"})
        summary = self.store.blocker_summary(24)
        self.assertEqual(summary["evaluations"], 2)
        self.assertEqual(summary["blocked"], 1)
        self.assertEqual(summary["by_stage"], {"strategy": 1})


if __name__ == "__main__":
    unittest.main()
