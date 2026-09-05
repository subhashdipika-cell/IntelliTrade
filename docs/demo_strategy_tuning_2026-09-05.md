# IntelliTrade DEMO strategy tuning — 2026-09-05

## Scope and safety

- Exact terminal: `D:\MT5IntelliTrade\terminal64.exe`
- Broker account reported `DEMO`; `ALLOW_LIVE=false`
- Scanner remains autonomous on DEMO and scheduled every 60 seconds.
- Signals use completed M30 candles; minute polling prevents missing a newly
  closed candle but does not create a trade every minute.
- ETH is disabled because no tested candidate met the deployment gate.

## Two-month execution audit

The last 62 days contained 68 local closed records. Only 23 were scanner
originated; those produced +$24.94, 43.5% wins and PF 1.30. Scanner results by
asset were Gold +$39.40 / PF 1.73, BTC -$7.56 / PF 0.61, and ETH -$6.90 / PF
0.32. Adopted, reconciled and unattributed records were excluded from strategy
selection. The previously deployed Donchian strategy had three scanner trades,
all losses, for -$11.91.

## Selected DEMO candidates

Backtests used 9,998 current completed MT5 DEMO M30 bars, 1% of
equity per historical trade, current observed fixed spreads (Gold $0.15, BTC
$17.01), Gold commission of $3/lot/side, and five chronological out-of-sample
folds.

| Asset | Rule | Trades | Return | Win rate | PF | Max DD | Positive OOS folds | Mean OOS return |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Gold | SMA 50/100 cross, 1.5 ATR SL, 2.2R TP, M30 | 101 | +35.95% | 41.58% | 1.53 | -9.48% | 5/5 | +3.44% |
| BTC | SMA 60/100 cross, 1.2 ATR SL, 2.2R TP, M30 | 98 | +27.74% | 41.84% | 1.43 | -9.53% | 5/5 | +4.08% |

Parameter-neighbour checks covered 63 variants per asset. Thirty-six variants
per asset remained profitable with PF >= 1.10, at least three positive folds,
and positive mean OOS return. This reduces, but does not eliminate, overfitting
risk.

## Live-DEMO risk behavior

Live DEMO sizing now uses equity, current broker-side entry price, stop
distance, tick size and tick value. The persisted 0.5% risk-per-trade setting is
the budget, while configured fixed lots are retained as hard maximums. Volumes
are rounded down to the broker step. If even the broker minimum lot exceeds the
risk budget, the order is refused.

## Caveats

Historical and walk-forward profitability is evidence, not a promise. Fixed
spread assumptions do not model every spread spike or all slippage. The live
pipeline's structure/news safeguards can reject some backtested signals, so
forward-DEMO frequency and results must be reviewed after a meaningful sample.
