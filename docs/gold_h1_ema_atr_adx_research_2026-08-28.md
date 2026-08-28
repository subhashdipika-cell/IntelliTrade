# Gold H1 EMA ATR ADX research — 2026-08-28

## Decision

Deploy `gold_h1_ema_atr_adx` to the MT5 DEMO scanner for XAUUSD only. The selected configuration favors walk-forward stability over the highest full-sample return:

- H1 completed candles only
- EMA 9/21 trend state, EMA 100 alignment and 5-bar slope
- ADX(14) >= 20
- ATR(14) breakout distance: 1.5 ATR from EMA 21
- ATR percentile regime: 20th through 95th percentile over 252 bars
- Entry session: 07:00–18:00 UTC, Monday–Friday
- Stop: 1.5 ATR
- Target: 2.0R
- One signal per EMA trend cycle

## Test design

- Source: 9,999 completed XAUUSD H1 bars from the connected Vantage Markets MT5 DEMO account
- Period: 2024-12-18 02:00 through 2026-08-28 13:00 broker time
- Initial equity: $1,000
- Risk per trade: 1%
- Costs: observed 0.11 spread plus $3 per lot per side commission
- Search: 32 bounded combinations across session, EMA alignment, ADX threshold, ATR percentile floor, and target R:R
- Validation: five chronological walk-forward folds

## Selected result

| Metric | Result |
|---|---:|
| Trades | 141 |
| Win rate | 37.59% |
| Profit factor | 1.18 |
| Net profit | $163.71 |
| Return | 16.37% |
| Maximum drawdown | 11.04% |
| Sharpe ratio | 0.75 |
| Positive walk-forward folds | 5 / 5 |
| Mean out-of-sample return | 3.33% |
| Walk-forward folds with PF >= 1.20 | 5 / 5 |

The selected candidate passed the bounded DEMO research gate. Variants with higher full-period returns were rejected because only four of five walk-forward folds were positive.

## Limitations and forward-test rule

This is historical evidence, not proof of future profitability. The deployment remains DEMO-only. Do not promote or increase risk based on this backtest. Reassess after at least 50 reconciled DEMO trades spanning 20 trading sessions, including spread, commission, slippage, signal rejections, and realised drawdown.

Reproduce the search from the repository root with:

```powershell
cd backend
python scripts/research_gold_h1_ema_atr_adx.py
```
