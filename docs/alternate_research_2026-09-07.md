# Alternate-family evaluation — 7 September 2026

## Decision

Both candidates failed the predeclared gate and remain research-only. No scanner
settings, risk limits or active strategies were changed. The execution pipeline
blocks either research class before signal generation. Registry entries become
available to the Backtest page after backend restart; no restart was performed.

## Rules fixed before evaluation

Gold: M30 range rejection. Require 20-bar efficiency ratio <=0.30 and candle
range <=2 ATR14. The previous close must be outside the previous bar's SMA20
plus/minus two population standard deviations, and the current close must
return inside that same boundary. Target is current SMA20. Stop is beyond the
two-bar extreme by 0.2 ATR, widened if necessary to 0.8 ATR; reject risk >2 ATR
or target reward/risk <1.5. Both directions use symmetric rules.

BTC: M30 volatility squeeze breakout. Previous ATR14 must be <=0.9 times its
80-bar rolling median. Candle range must be 0.8–2 ATR. Close must break the
prior 20-bar extreme from inside that boundary, finishing in the outer quarter
of the candle. Stop is 1.5 ATR, target 2.5R. Both directions are permitted.

Neither hypothesis uses funding, news or session data. These are initial
OHLC hypotheses, not claims of institutional or published trading edges.

## Evaluation

Same simulator as the preceding continuation experiment: 9,999 completed M30
bars each; chronological 50/25/25 split; next-open entries; adverse slippage;
bid/ask-aware SELL exits; stop-first ambiguity; adverse stop gaps; broker lot
steps/minimums/caps; 0.5% risk ceiling on $10,000; normal and doubled spreads.
Gold assumes $6 commission per lot round trip and BTC zero. Each segment starts
flat and ends liquidated. Swap, live trailing/news filters, historical contract
changes and dynamic spreads are excluded. Drawdown is close-marked.

This history has been inspected in prior experiments. These are chronological
test segments, not pristine unseen data. Repeated family testing increases
selection bias; no parameter tuning followed this result.

| Candidate | Validation trades | Validation PF | Holdout trades | Holdout PF | Holdout return |
|---|---:|---:|---:|---:|---:|
| Gold range reversal | 13 | 0.605 | 11 | 1.167 | +0.471% |
| BTC squeeze breakout | 14 | 0.617 | 21 | 0.551 | -2.884% |

At doubled spreads holdout PF is 1.157 for Gold and 0.518 for BTC.
Gold lacks sample size and failed validation; BTC lost in every segment.
Neither demonstrated a reliable increase in profitable trade opportunities.

Gate: both validation and holdout require >=20 trades, normal-spread PF >=1.2,
stressed PF >=1, positive stressed return and stressed drawdown <=5%.

Current M30 baselines still performed better in the final segment but also
lost in validation. The new results do not prove the active strategies robust.

Run from backend: `.venv\Scripts\python.exe -B research_alternate.py`.
The dated JSON contains all segment metrics and is overwritten on rerun.
It uses the latest broker history and current spread/specs, so values can vary.

## Remaining research need

Four candidates across two rounds have now failed. A broader blind search on
this same history would invite overfitting. Further research should first
freeze a dataset and improve execution validation, then evaluate a limited
set of predeclared hypotheses on genuinely separate data and forward samples.
