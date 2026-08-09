# IntelliTrade

A personal, laptop-based algorithmic trading operating system for **BTC, ETH and Gold** on
Vantage MT5. Built around a **traceable pipeline**, not a pile of features.

```
Market → Analysis → Strategy → AI Filter → Wiki Filter → Risk → Execution → Monitoring → Learning
```

Every stage records a decision into the `TradeContext` so you can always answer
*"Why did IntelliTrade buy Gold here?"*.

## MVP scope (deliberately small)

Seven pages only. Everything else (Strategy Marketplace, AI Lab, Optimization UI,
Portfolio, News Center, Trade Replay, plugin system) is deferred until the core loop
has run live-on-Demo for several weeks.

| Page         | Purpose                                          |
|--------------|--------------------------------------------------|
| Dashboard    | Command center: status, P/L, open trades, logs   |
| Backtest     | Vectorized backtest **with walk-forward**         |
| Live         | Approved strategies, pipeline run feed            |
| History      | Closed trades + monthly analysis                  |
| Journal      | Notes, writes back to Obsidian vault              |
| Money Mgmt   | Live equity, lot size, daily-loss %, RR, override |
| Settings     | MT5 creds, Obsidian path, Telegram config         |

## Safety posture

- **Live trading is gated**, not a casual toggle. The executor refuses to place a real-money
  order unless `ALLOW_LIVE=true` *and* MT5 is verified logged into the expected account type.
- The **AI filter and Wiki filter default to pass-through / advisory** and only *log* their
  opinion until you explicitly let them block. The edge must come from strategy + risk rules.
- Backtests run **walk-forward / out-of-sample** so you don't ship an overfit curve.

## Telegram alerts

- On **trade entry**: asset, entry, SL, target, capital deployed, total capital.
- On **trade close**: asset, outcome (SL / TSL / TGT), total capital after the trade.

See `backend/app/services/telegram.py` and the wiring in
`backend/app/pipeline/stages/execution.py` and `monitoring.py`.

## Price-action scalp strategy

`price_action_scalp` is available in Backtest and Live. It models a discretionary
chart read as a causal **range break → retest → rejection candle** setup. It uses
OHLC price action for the setup and ATR only to normalize stops and reject trades
with excessive risk. It scans M5 bars and uses a default 1.8R target.

Deploy it in `alert_only` mode first. In the Live page or `/api/scanner/settings`,
select `price_action_scalp` for GOLD and/or BTC. Do not switch it to autonomous
until it has passed walk-forward testing with the actual symbol contract,
spread, commission, and several weeks of demo forward testing.

## Running (everyday)

1. Open the **Vantage MT5 terminal** and log in to your **DEMO** account.
2. Double-click **`Start-IntelliTrade.bat`** in this folder.
   - It opens two windows (Backend `:8100`, Frontend `:3000`) and your browser at
     http://localhost:3000.
   - To **stop**: close those two windows.

Or run the two servers manually:

```bat
:: window 1 — backend
cd D:\IntelliTrade\backend
python -m uvicorn main:app --port 8100

:: window 2 — frontend
cd D:\IntelliTrade\frontend
npm run dev
```

Then open http://localhost:3000.

## First-time setup (already done on this machine)

```bat
cd D:\IntelliTrade\backend
pip install -r requirements.txt          :: + scikit-learn joblib
copy ..\.env.example ..\.env             :: then fill in credentials
cd ..\frontend && npm install
```

> **Windows-only:** the official `MetaTrader5` Python package runs only on Windows,
> and the app attaches to the running terminal — so MT5 must be open and logged in
> before you start the backend. This app is chained to your laptop being on — fine
> for a personal tool.
