# CLAUDE.md — IntelliTrade

Project context for any new session. Read this first.

## What it is
Personal, laptop-based (Windows-only) algorithmic trading app for **BTC, ETH, Gold**
on Vantage MT5. **Backend** = Python/FastAPI (`backend/`), **frontend** = Next.js 15
(`frontend/`). One user (subhash.dipika@gmail.com). Not a git repo.

## How to run
Open the MT5 terminal first (`D:\MT5IntelliTrade`, logged into the demo account), then
double-click **`Start-IntelliTrade.bat`**. It self-cleans ports 8100/3000 and launches:
- **Backend** → http://localhost:8100  (uvicorn `main:app`)
- **Frontend** → http://localhost:3000  (Next proxies `/api/*` → `:8100`, see `next.config.js`)

`.env` changes (credentials, ALLOW_LIVE, etc.) require a **backend restart** to take effect.
Don't run `npm run build` while `npm run dev` is running (corrupts `.next`).

## Architecture — a traceable pipeline
`Market → Analysis → Strategy → AI Filter → Wiki Filter → Risk → Execution → Monitoring → Learning`
Every stage stamps a `Decision` onto the `TradeContext` (`backend/app/pipeline/context.py`)
so you can answer "why did it trade here?". Pipeline assembled in `app/pipeline/factory.py`.
- **Strategies** (`app/strategies/`, registry.py): sma_crossover, donchian_breakout, ema_pullback,
  macd_cross, rsi_reversion, bollinger_reversion. Selectable in Backtest & Live. Each implements a
  shared `_series()` (indicators once) + `_decide_at(i)` (scalar rule); `generate()` (live, last bar)
  and `signals()` (vectorised, one per bar) both reuse them, so backtests are **O(n)** not O(n²).
  A new strategy should implement `signals()` (or inherit the slow default in `base.py`).
- **AI filter** + **Wiki filter** default to **advisory** (log, don't block) until trusted.
  Wiki = ForexFactory-independent; LLM via OpenRouter (`app/obsidian_rag/wiki_validator.py`).
- **Auto-scanner** (`app/workers/signal_scanner.py`, every 60s): runs deployed strategies on each
  new closed bar. Modes: **alert_only** (Telegram only) / **autonomous** (auto-places). Config in
  `app/services/scanner_store.py`.
- **Monitor** (`app/workers/trade_monitor.py`, every 15s): detects closes, fires exit alert,
  **reconciles from MT5 deal history** so no closed trade is ever missed (survives restarts; recent
  reconciled closes also alert), **re-attaches open positions on startup**
  (`monitoring.reattach_open_trades`, called in `main.lifespan`) so a trade left open across a restart
  keeps its tracking → exit alert + trailing + vault-log still fire on close, and
  **trails open stops** (`app/services/trailing.py`): 3-stage ratchet — breakeven → ATR/R trail →
  near-target tighten. Triggers are % of distance-to-target (RR-agnostic), give-backs in units of
  R = |entry−origSL|. `signal.stop_loss` stays ORIGINAL so a trailed exit still classifies as TSL.
- **Smart targets** (`StrategyStage._cap_target_to_structure`): caps a signal's target just below
  the nearest swing resistance/support (strategy-agnostic; breakouts at fresh highs self-exempt).
  Both features + thresholds live in Money Mgmt settings (`trailing_enabled`, `target_cap_enabled`).
- **Vault auto-log** (`app/services/vault_export.py`, `obsidian_autolog_enabled`): each closed trade
  (on the tracked-close path) and a **weekly all-strategies×assets backtest snapshot** are written to
  the Obsidian vault (`…\raw\trades`, `…\raw\backtests`) as markdown+frontmatter + a JSON data block,
  each tagged with a **market regime** (`app/services/regime.py`: trend via EMA50/200+ADX, vol via
  ATR percentile). Feeds the Wiki RAG + Strategy Review for "which strategy fits which regime".

## Pages (frontend, 8)
Dashboard (charts + session bar + events ticker), Backtest (engine + walk-forward + per-lot
commission + Compare-All-Strategies matrix + **data source: MT5-live or imported offline CSV**),
Live (run pipeline + decision tree + Auto-Scanner),
History (trades + decision trees + **Monthly Report** + strategy×asset matrix), **Review**
(LLM-assisted Strategy Review — reads real closed-trade performance, returns concrete refinement
suggestions; read-only/advisory), Money Mgmt (equity + guardrails + **per-asset lot sizes** +
DEMO/LIVE toggle), Journal (Obsidian writeback + analysis), Settings (Telegram test). Logo lives in
the sidebar (click = refresh).

## Ports, MT5 terminals, accounts (3 apps coexist on this machine)
| App | Frontend | Backend | MT5 terminal | Order magic |
|---|---|---|---|---|
| **IntelliTrade** | 3000 | 8100 | `D:\MT5IntelliTrade` (its own) | 770011 |
| smart-money-trader | 5173 | 8000 | `C:\Program Files\Vantage Markets MT5 Terminal` (shared) | 20260101 / 202609 |
| alphaedge | 5001 | 5000 (bridge) | shares the Vantage terminal | 532025 |

Each app pins its terminal via `mt5.initialize(path=...)` so they never grab each other's. Demo
account 25600027 on `VantageMarkets-Demo`. Identify any order's origin by its magic / comment.

## Safety
- **Live trading is gated:** real-money orders / switching to LIVE need `ALLOW_LIVE=true` AND the
  terminal verified as the expected account type (auto-reverts to DEMO otherwise).
- Live and Demo profiles both point at `D:\MT5IntelliTrade`; switching re-logs that terminal.
- `mt5_client.place_order` builds the order with magic 770011 + comment "IntelliTrade".
- Never execute trades on the user's behalf — the scanner/UI does that with the user's config.

## Outcome classification (fixed 2026-06)
Closed trades classified by the **actual MT5 deal reason** (`_deal_reason_str` in mt5_client):
SL→SL, TP→TGT, trailed-stop→TSL, else MANUAL. (Earlier bug labelled every SL hit as TSL — fixed.)

## State files (`backend/app/data/`, all gitignored)
`money_settings.json`, `scanner_settings.json`, `trade_history.jsonl` (closed trades),
`calendar_cache.json`, `models/<ASSET>_filter.joblib` (ML filters, bootstrapped on price history),
`market/<ASSET>_<TF>.csv` (offline OHLCV imported + deduped from AlphaEdge's collector, for
backtesting; source dir = `alphaedge_data_dir` in config, default `D:\alphaedge\strategy-lab\data`).

## Key endpoints (under `/api`)
`/live/run`, `/live/test-trade`, `/live/monitored`, `/backtest/run`, `/backtest/matrix`,
`/backtest/import-data`, `/backtest/datasets`, `/backtest/snapshot`,
`/history/trades`, `/history/monthly-report`, `/history/strategy-matrix`, `/review/strategies`,
`/account/info`,
`/account/switch`, `/money/overview|settings`, `/scanner/settings`, `/ai/train`, `/news/events`,
`/journal/save`, `/telegram/test-entry|test-exit`.

## Recurring gotchas
- Background uvicorn launches report a spurious "exit 127" — check the port, it's usually fine.
- **MT5 `deal.time` is BROKER-SERVER time** (can run hours ahead of the laptop clock). Any
  `history_deals_get(frm, to)` must use a wide `to` (e.g. `now + 1 day`) or just-closed trades get
  clipped and never reconciled into History. Bit us once (a Gold TP went missing); fixed in
  `mt5_client.closed_trades_by_magic`. Don't rebuild the window from local `now()` tightly.
- Free ForexFactory feed rate-limits (429); calendar is cached 6h + serves stale. Don't poll it.
- LLM (Wiki gatekeeper) is OpenAI-compatible with two providers via `LLM_PROVIDER`:
  `openrouter` (key in `OPENAI_API_KEY` + namespaced model) or `ollama` (local/free, no key,
  `OLLAMA_BASE_URL`, model = a pulled tag like `llama3`/`mistral`/`qwen2.5`). All calls go through
  `app/services/llm.py` (`chat()` + `extract_json()`). **Strategy Review overrides the provider**
  (`REVIEW_PROVIDER`/`REVIEW_MODEL`, default OpenRouter) because its ~500-token JSON is too slow on a
  local CPU model — so the gatekeeper can stay on Ollama while Review runs on cloud (~5s vs ~90s).

## More detail
See the auto-memory files (loaded each session): intellitrade-overview, -telegram-alerts,
-backtest-costs, -events-ticker.
