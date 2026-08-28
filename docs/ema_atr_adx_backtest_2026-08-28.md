# EMA ATR ADX Trend Signals — historical backtest

Date: 2026-08-28
Scope: historical research only; no deployment or profitability claim.

## Method

- Data: 9,999 completed Vantage MT5 DEMO bars per asset/timeframe.
- Assets: BTCUSD, ETHUSD, XAUUSD+.
- Timeframes: M5, M15, H1.
- Initial capital: $1,000; risk: 1% of current equity per trade.
- Entry: confirmed signal-bar close plus the current broker spread.
- Exit: one target per run; TP1 = 1.5R or TP2 = 2.5R.
- Ambiguous bar: stop checked before target.
- Costs: current fixed spread (BTC 16.99, ETH 2.51, Gold 0.11 price units);
  Gold commission $3 per lot per side; configured crypto commission $0.
- Walk-forward: five chronological folds, scoring the final 30% of each fold.

The supplied Pine code is an indicator, not a TradingView strategy. It draws two
targets but does not define partial sizing or exit execution. IntelliTrade uses a
configurable single `target_rr`; both Pine target values were tested separately.

## Results

| Asset | TF | Target | Trades | Win % | PF | Return % | Max DD % | Positive WF folds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | M5 | 1.5R | 215 | 43.72 | 0.77 | -25.94 | -34.42 | 2/5 |
| BTC | M5 | 2.5R | 206 | 28.64 | 0.69 | -38.18 | -42.20 | 2/5 |
| BTC | M15 | 1.5R | 226 | 38.94 | 0.80 | -22.86 | -28.66 | 2/5 |
| BTC | M15 | 2.5R | 220 | 27.27 | 0.80 | -26.51 | -27.76 | 1/5 |
| BTC | H1 | 1.5R | 233 | 39.48 | 0.92 | -9.78 | -18.94 | 4/5 |
| BTC | H1 | 2.5R | 215 | 28.84 | 0.96 | -5.93 | -14.29 | 3/5 |
| ETH | M5 | 1.5R | 223 | 33.18 | 0.31 | -62.46 | -63.25 | 0/5 |
| ETH | M5 | 2.5R | 207 | 23.67 | 0.35 | -64.58 | -64.58 | 0/5 |
| ETH | M15 | 1.5R | 204 | 41.18 | 0.65 | -33.92 | -36.45 | 1/5 |
| ETH | M15 | 2.5R | 185 | 34.05 | 0.84 | -16.97 | -23.77 | 2/5 |
| ETH | H1 | 1.5R | 218 | 42.20 | 0.95 | -6.27 | -14.47 | 2/5 |
| ETH | H1 | 2.5R | 206 | 27.67 | 0.86 | -20.22 | -27.12 | 1/5 |
| GOLD | M5 | 1.5R | 215 | 41.40 | 1.00 | +0.23 | -16.86 | 1/5 |
| GOLD | M5 | 2.5R | 193 | 29.02 | 0.97 | -4.41 | -20.98 | 0/5 |
| GOLD | M15 | 1.5R | 205 | 45.37 | 1.21 | +25.95 | -14.46 | 2/5 |
| GOLD | M15 | 2.5R | 199 | 33.67 | 1.23 | +34.95 | -13.71 | 2/5 |
| GOLD | H1 | 1.5R | 215 | 41.40 | 1.03 | +3.90 | -15.47 | 2/5 |
| GOLD | H1 | 2.5R | 206 | 31.55 | 1.12 | +18.35 | -13.26 | 4/5 |

## Decision

- Reject BTC and ETH deployment: every tested variant had negative full-period
  return and PF below 1.0.
- Do not autonomously deploy Gold M15 yet: full-period PF was 1.21–1.23, but only
  two of five walk-forward folds were positive.
- Gold H1 TP2 is the most stable research candidate (four of five positive
  walk-forward folds), but PF 1.12 and 13.26% drawdown miss the current quality
  bar. Keep it selectable for research/backtesting and collect further evidence
  before adding it to DEMO autonomous scanning.

Reproduce with:

```powershell
$env:PYTHONPATH='D:\IntelliTrade\backend'
D:\IntelliTrade\backend\.venv\Scripts\python.exe D:\IntelliTrade\backend\scripts\run_ema_atr_adx_backtest.py
```
