# Reproducible research and future validation

Implemented 7 September 2026. This changes the standalone research simulator,
not the application's legacy Backtest engine or active execution settings.

## Simulator version 2

- Validates ordered unique timestamps, finite positive prices and OHLC ranges.
- Validates contract values, volume bounds and spread inputs.
- Uses previous completed signal / next-open entry, recording both timestamps.
- Known gap openings take precedence over later intrabar touches. Ambiguous
  intrabar paths still use stop first. Stop gaps incur adverse fills; target
  gaps receive the target price with no favorable improvement.
- Planned position risk now includes stop-exit slippage and commission.
- Every closed trade has an auditable ledger with entry, exit, side, volume,
  reason and net P&L. Segment ends liquidate remaining positions.

The model still omits swap/funding, dynamic historical spreads, live trailing
and news rules, intrabar equity extremes, and changing broker specifications.
It uses current contract terms, tick-value conversion, conservative OHLC fills,
0.5% risk budget, and fixed lot caps. It is not tick-level execution proof.

## Frozen local dataset

Directory: `D:\IntelliTrade\backend\app\data\research\freeze-20260907-v2`

Contains 9,999 completed M30 bars each for Gold and BTC, ending at broker label
`2026-09-07 05:00:00`, plus a JSON manifest with SHA256 hashes, frozen contract
specifications, capture UTC and source hashes. These bars are explicitly
previously inspected development history, not unseen validation data.

Files are exclusive-create; the tool refuses to overwrite an existing snapshot.
Loading verifies each CSV checksum. Filesystem permissions do not prevent a user
from editing both files and manifests; retain a trusted manifest copy. The v2
report committed in docs embeds this initial manifest. CSVs stay in the ignored
local data directory, so a GitHub clone alone cannot reproduce the experiment.
Back up the complete snapshot directory along with the report.

## Separate future window

Eligible forward bars begin at broker label `2026-09-07 06:30:00`, excluding the
forming candle at capture and one additional bar. Broker timestamps are not
assumed UTC. The initial capture was 02:51 UTC; the live broker labels were
approximately three hours ahead. If terminal clock conventions change, stop
and reconcile timestamps before merging batches.

At creation, eligible forward rows are **zero**. No future-performance result
exists yet. This defines a new window; it cannot create future observations.

The collector runs only when invoked; no recurring task was created. It writes
dated batches without replacing development data and excludes overlap with
that data. Batches can overlap each other: deduplicate by timestamp when
assembling validation data and investigate conflicting duplicate prices.
Ten thousand requested bars are a rolling retrieval limit; collect regularly
or expand retrieval before older forward bars leave that window. Check gaps.

Minimum review policy: 60 calendar days and 30 completed trades per asset,
PF >=1.2 at normal costs, PF >=1 at doubled spreads, positive stressed return,
and drawdown <=5%. This policy is recorded for review, not automatic promotion.
Freeze hypothesis/code before collection; source changes are flagged and require
a new window. Do not tune to forward results and continue calling them unseen.
Do not automatically enable a strategy based on these thresholds alone.

## Commands (from D:\IntelliTrade\backend)

Verify snapshot, without contacting MT5:

```powershell
.\.venv\Scripts\python.exe -B research_dataset.py verify D:\IntelliTrade\backend\app\data\research\freeze-20260907-v2
```

Reproduce alternate-family comparison offline:

```powershell
.\.venv\Scripts\python.exe -B research_frozen.py D:\IntelliTrade\backend\app\data\research\freeze-20260907-v2
```

Collect newly completed forward bars from the configured DEMO terminal:

```powershell
.\.venv\Scripts\python.exe -B research_dataset.py collect-forward D:\IntelliTrade\backend\app\data\research\freeze-20260907-v2
```

Tests cover gap order, stop-first ambiguity, next-open timestamps, malformed
data, checksum tampering, overwrite refusal and exclusion of development bars.
The complete suite passes 19 tests. Offline repeat reports are hash-identical.
