# Continuation strategy evaluation — 7 September 2026

## Decision

Neither candidate is approved for DEMO execution. Existing scanner settings
were not changed. Both registry entries are blocked in StrategyStage even if
selected through the Live page or scanner settings. They are available for
backtesting after backend restart.

Gold uses a SMA20 reclaim through the previous candle extreme, aligned with
SMA60 direction and slope. BTC uses a three-bar countertrend pause and range
breakout, aligned with SMA20/SMA80 and above-average broker tick activity.
Both use volatility/shock filters and swing-aware ATR stops. Full mechanical
rules are in continuation_research.py under app/strategies. No session filter
is used in this initial experiment; exchange funding and broker clock session
mapping are not inferred from OHLC bars.

## Method

9,999 completed M30 broker bars per instrument. Fixed parameters, chronological
50% development / 25% validation / 25% holdout. This history overlaps previously
inspected data and is not a pristine independent holdout. No parameter search
or post-holdout tuning was performed. Each segment starts flat with $10,000.
Entry is the next bar's open, with spread and adverse slippage; SELL exits use
ask-adjusted prices. Ambiguous bars hit stops first; stop gaps get adverse open
fills. Position sizes use broker tick values, volume steps and minimums, 0.5%
risk budget and current fixed-lot caps. End positions are liquidated.

Spread is the current observed spread at 1x and 2x. Gold commission assumes
$6/lot round trip; BTC commission assumes zero. Swap, funding, historical
specification changes, latency and live trailing/news overlays are excluded.
Drawdown is close-marked and may understate intrabar equity drawdown.
Entry minimum reward/risk is 1.5. These assumptions differ from the earlier
simpler research engine, so the results are not directly interchangeable.

## Results at normal spread

| Candidate | Validation trades | Validation PF | Holdout trades | Holdout PF |
|---|---:|---:|---:|---:|
| Gold continuation | 31 | 0.801 | 36 | 1.025 |
| BTC continuation | 15 | 0.788 | 5 | 0.526 |

At doubled spreads, holdout PF was 1.018 for Gold and 0.454 for BTC.
Gold generated more trades without a convincing edge. BTC did not increase
frequency reliably. Promotion required at least 20 trades in each later
segment, normal-spread PF >=1.2, stressed PF >=1, positive stressed returns
and stressed drawdown <=5%. Both failed.

The existing M30 baselines also lost in validation (Gold PF 0.860, BTC 0.696)
despite profitable holdouts. Their aggregate profitability therefore does not
establish stability across regimes. Do not increase risk or claim profitability
based on these experiments. No trade was placed by the research program.

Run from backend: `.venv\Scripts\python.exe -B research_continuation.py`.
This reads the configured DEMO terminal and overwrites the dated JSON report;
results can change as history rolls forward. Detailed per-segment metrics
are in continuation_research_2026-09-07.json.
