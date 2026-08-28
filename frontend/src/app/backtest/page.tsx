"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { EquityCurve } from "@/components/EquityCurve";

const STRAT_LABELS: Record<string, string> = {
  sma_crossover: "SMA Crossover",
  donchian_breakout: "Donchian Breakout",
  ema_pullback: "EMA Pullback",
  ema_pullback_scalp: "EMA Pullback Scalp (Gold M1/M5)",
  ema_atr_adx_trend: "EMA ATR ADX Trend Signals",
  gold_h1_ema_atr_adx: "Gold H1 EMA ATR ADX",
  macd_cross: "MACD Cross",
  rsi_reversion: "RSI Reversion",
  bollinger_reversion: "Bollinger Reversion",
};

interface Metrics {
  total_return_pct: number;
  gross_return_pct: number;
  final_balance: number;
  net_profit: number;
  gross_profit: number;
  total_commission: number;
  commission_drag_pct: number;
  total_lots_traded: number;
  total_trades: number;
  win_rate_pct: number;
  profit_factor: number | null;
  avg_win: number;
  avg_loss: number;
  avg_commission_per_trade: number;
  max_drawdown_pct: number;
  sharpe: number;
}

interface Trade {
  time: string;
  direction: string;
  entry: number;
  exit: number;
  lots: number;
  reason: string;
  gross_pnl: number;
  commission: number;
  pnl: number;
}

interface WalkForward {
  folds: { fold: number; oos_bars: number; oos_metrics: Metrics }[];
  summary: {
    mean_oos_return_pct: number;
    positive_folds: number;
    total_folds: number;
    consistency: number;
  };
}

interface BacktestResponse {
  error?: string;
  metrics: Metrics;
  trades: Trade[];
  equity_curve: number[];
  commission_per_lot_used: number;
  walk_forward?: WalkForward;
}

const DEFAULTS = {
  asset: "GOLD",
  timeframe: "H1",
  strategy: "sma_crossover",
  count: 3000,
  initial_capital: 1000,
  spread: 0,
  commission_per_lot: 3,
  commission_pct: 0,
  commission_per_trade: 0,
  walk_forward: true,
  source: "mt5",
};

// Tunable parameters per strategy (label, default, integer?, step). The Backtest
// form renders these dynamically and sends them as strategy_params; the backend
// keeps only the keys each strategy accepts.
interface ParamSpec { k: string; label: string; def: number; int?: boolean; step?: number; }
const STRAT_PARAMS: Record<string, ParamSpec[]> = {
  sma_crossover: [
    { k: "fast", label: "Fast MA", def: 50, int: true },
    { k: "slow", label: "Slow MA", def: 200, int: true },
  ],
  ema_pullback: [
    { k: "fast", label: "Fast EMA", def: 20, int: true },
    { k: "mid", label: "Mid EMA", def: 50, int: true },
    { k: "slow", label: "Slow EMA", def: 200, int: true },
    { k: "rr", label: "Reward:Risk", def: 2, step: 0.1 },
  ],
  ema_pullback_scalp: [
    { k: "fast", label: "Fast EMA", def: 9, int: true },
    { k: "mid", label: "Mid EMA", def: 21, int: true },
    { k: "slow", label: "Slow EMA", def: 50, int: true },
    { k: "sl_pips", label: "SL (pips)", def: 500 },
    { k: "tp_pips", label: "TP (pips)", def: 1500 },
    { k: "pip_size", label: "Pip size", def: 0.01, step: 0.01 },
  ],
  macd_cross: [{ k: "rr", label: "Reward:Risk", def: 2, step: 0.1 }],
  ema_atr_adx_trend: [
    { k: "fast_ema_length", label: "Fast EMA", def: 9, int: true },
    { k: "slow_ema_length", label: "Slow EMA", def: 21, int: true },
    { k: "atr_length", label: "ATR Length", def: 14, int: true },
    { k: "atr_multiplier", label: "ATR Breakout Multiplier", def: 1.5, step: 0.1 },
    { k: "sl_atr_multiple", label: "Stop-Loss ATR Multiple", def: 1.5, step: 0.1 },
    { k: "target_rr", label: "Executable Target R:R (TP1 1.5 / TP2 2.5)", def: 2.5, step: 0.1 },
    { k: "adx_length", label: "DI Length", def: 14, int: true },
    { k: "adx_smoothing", label: "ADX Smoothing", def: 14, int: true },
    { k: "adx_threshold", label: "ADX Threshold", def: 20, step: 0.5 },
    { k: "volume_length", label: "Volume Average Length", def: 20, int: true },
    { k: "volume_multiplier", label: "High-Volume Multiplier", def: 1.5, step: 0.1 },
  ],
  gold_h1_ema_atr_adx: [
    { k: "atr_multiplier", label: "ATR Breakout Multiplier", def: 1.5, step: 0.1 },
    { k: "sl_atr_multiple", label: "Stop-Loss ATR Multiple", def: 1.5, step: 0.1 },
    { k: "target_rr", label: "Target R:R", def: 2.0, step: 0.1 },
    { k: "adx_threshold", label: "ADX Threshold", def: 20, step: 0.5 },
    { k: "long_ema_length", label: "Long EMA", def: 100, int: true },
    { k: "min_atr_percentile", label: "Minimum ATR Percentile", def: 20, step: 5 },
    { k: "max_atr_percentile", label: "Maximum ATR Percentile", def: 95, step: 5 },
    { k: "session_start_utc", label: "Session Start UTC", def: 7, int: true },
    { k: "session_end_utc", label: "Session End UTC", def: 18, int: true },
  ],
  donchian_breakout: [
    { k: "channel", label: "Channel", def: 20, int: true },
    { k: "rr", label: "Reward:Risk", def: 2, step: 0.1 },
  ],
  rsi_reversion: [
    { k: "period", label: "RSI Period", def: 14, int: true },
    { k: "oversold", label: "Oversold", def: 30 },
    { k: "overbought", label: "Overbought", def: 70 },
    { k: "rr", label: "Reward:Risk", def: 1.5, step: 0.1 },
  ],
  bollinger_reversion: [
    { k: "period", label: "Period", def: 20, int: true },
    { k: "k", label: "Std-Dev (k)", def: 2, step: 0.1 },
    { k: "rr", label: "Reward:Risk", def: 1.5, step: 0.1 },
  ],
};
const defaultParams = (strat: string): Record<string, number> =>
  Object.fromEntries((STRAT_PARAMS[strat] ?? []).map((p) => [p.k, p.def]));

const money = (v: number) =>
  `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const pctColor = (v: number) => (v >= 0 ? "text-emerald-400" : "text-rose-400");

const INPUT =
  "bg-[#0d1117] border border-gray-700 rounded px-2 py-2 text-xs w-full outline-none focus:border-amber-600";

interface MatrixCell {
  return_pct: number;
  win_rate_pct: number;
  profit_factor: number | null;
  max_dd_pct: number;
  trades: number;
  error?: string;
}
interface MatrixResp {
  assets: string[];
  strategies: string[];
  grid: Record<string, Record<string, MatrixCell>>;
}

export default function BacktestPage() {
  const [form, setForm] = useState(DEFAULTS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [res, setRes] = useState<BacktestResponse | null>(null);
  const [matrix, setMatrix] = useState<MatrixResp | null>(null);
  const [matrixLoading, setMatrixLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState("");
  const [strats, setStrats] = useState<string[]>(["sma_crossover", "donchian_breakout"]);

  useEffect(() => {
    api.backtestStrategies()
      .then((d) => setStrats((d as { strategies: string[] }).strategies))
      .catch(() => {});
  }, []);

  const [params, setParams] = useState<Record<string, number>>(defaultParams(DEFAULTS.strategy));

  const set = (k: keyof typeof DEFAULTS, v: number | string | boolean) =>
    setForm((f) => ({ ...f, [k]: v }));

  const setParam = (k: string, v: number) => setParams((p) => ({ ...p, [k]: v }));

  // Switching strategy resets its parameters to that strategy's defaults.
  const onStrategyChange = (s: string) => {
    set("strategy", s);
    setParams(defaultParams(s));
  };

  async function importData() {
    setImporting(true);
    setImportMsg("");
    try {
      const r = (await api.importMarketData()) as {
        ok?: boolean; error?: string; datasets?: Record<string, { rows: number }>;
      };
      if (!r.ok) {
        setImportMsg(`❌ ${r.error ?? "Import failed."}`);
      } else {
        const total = Object.values(r.datasets ?? {}).reduce((s, d) => s + (d.rows || 0), 0);
        const sets = Object.keys(r.datasets ?? {}).length;
        setImportMsg(`✅ Imported ${total.toLocaleString()} bars across ${sets} datasets.`);
        set("source", "imported");
      }
    } catch {
      setImportMsg("❌ Import request failed.");
    } finally {
      setImporting(false);
    }
  }

  async function runMatrix() {
    setMatrixLoading(true);
    setError("");
    try {
      const d = (await api.backtestMatrix({
        timeframe: form.timeframe, count: form.count, source: form.source,
      })) as MatrixResp;
      setMatrix(d);
    } catch {
      setError("Matrix request failed — is the backend running on :8100?");
    } finally {
      setMatrixLoading(false);
    }
  }

  async function run() {
    setLoading(true);
    setError("");
    setRes(null);
    try {
      const data = (await api.runBacktest({ ...form, strategy_params: params })) as BacktestResponse;
      if (data.error) setError(data.error);
      else setRes(data);
    } catch {
      setError("Request failed — is the backend running on :8100?");
    } finally {
      setLoading(false);
    }
  }

  const m = res?.metrics;

  return (
    <div className="p-6 space-y-6 max-w-6xl">
      <h2 className="text-2xl font-bold">Backtest</h2>

      {/* ── Inputs ─────────────────────────────────────────────── */}
      <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Field label="Asset">
            <select
              value={form.asset}
              onChange={(e) => set("asset", e.target.value)}
              className={INPUT}
            >
              <option>GOLD</option>
              <option>BTC</option>
              <option>ETH</option>
            </select>
          </Field>
          <Field label="Timeframe">
            <select
              value={form.timeframe}
              onChange={(e) => set("timeframe", e.target.value)}
              className={INPUT}
            >
              {["M1", "M5", "M15", "M30", "H1", "H4", "D1"].map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </Field>
          <Field label="Data Source">
            <select
              value={form.source}
              onChange={(e) => set("source", e.target.value)}
              className={INPUT}
            >
              <option value="mt5">MT5 (live)</option>
              <option value="imported">Imported (offline)</option>
            </select>
          </Field>
          <Field label="Strategy">
            <select
              value={form.strategy}
              onChange={(e) => onStrategyChange(e.target.value)}
              className={INPUT}
            >
              {strats.map((s) => (
                <option key={s} value={s}>{STRAT_LABELS[s] ?? s}</option>
              ))}
            </select>
          </Field>
          <Num label="Bars" k="count" form={form} set={set} />
          <Num label="Initial Capital" k="initial_capital" form={form} set={set} />
          <Num label="Spread (price)" k="spread" form={form} set={set} step={0.01} />
          <Num label="Commission / lot / side" k="commission_per_lot" form={form} set={set} step={0.1} />
        </div>

        {/* Strategy parameters — dynamic per selected strategy */}
        {(STRAT_PARAMS[form.strategy]?.length ?? 0) > 0 && (
          <div className="mt-4 border-t border-gray-800 pt-4">
            <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">
              {STRAT_LABELS[form.strategy] ?? form.strategy} parameters
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {STRAT_PARAMS[form.strategy].map((p) => (
                <Field key={p.k} label={p.label}>
                  <input
                    type="number"
                    step={p.step ?? (p.int ? 1 : 0.01)}
                    value={params[p.k] ?? p.def}
                    onChange={(e) =>
                      setParam(p.k, p.int ? parseInt(e.target.value) || 0 : parseFloat(e.target.value) || 0)
                    }
                    className={INPUT}
                  />
                </Field>
              ))}
            </div>
          </div>
        )}

        <div className="flex items-center gap-4 mt-4">
          <label className="flex items-center gap-2 text-xs text-gray-400">
            <input
              type="checkbox"
              checked={form.walk_forward}
              onChange={(e) => set("walk_forward", e.target.checked)}
            />
            Walk-forward validation
          </label>
          <button
            onClick={importData}
            disabled={importing}
            title="Consolidate AlphaEdge's collector CSVs into IntelliTrade for offline / intraday backtesting"
            className="px-4 py-2 border border-gray-700 text-gray-300 hover:bg-gray-800 disabled:opacity-50 rounded-lg text-xs font-semibold"
          >
            {importing ? "Importing…" : "Import from AlphaEdge"}
          </button>
          {importMsg && <span className="text-xs text-gray-400">{importMsg}</span>}
          <button
            onClick={runMatrix}
            disabled={matrixLoading}
            title="Backtest every strategy on every asset"
            className="ml-auto px-5 py-2 border border-indigo-700 text-indigo-300 hover:bg-indigo-950/40 disabled:opacity-50 rounded-lg text-sm font-semibold"
          >
            {matrixLoading ? "Comparing…" : "Compare All Strategies"}
          </button>
          <button
            onClick={run}
            disabled={loading}
            className="px-6 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 rounded-lg text-sm font-bold"
          >
            {loading ? "Running…" : "Run Backtest"}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-rose-950/40 border border-rose-900/50 text-rose-300 text-sm rounded-lg p-4">
          {error}
        </div>
      )}

      {/* Strategy comparison matrix */}
      {matrix && (
        <div className="bg-[#0a0d12] border border-indigo-900/50 rounded-xl p-5">
          <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-400 mb-1">
            Strategy Comparison — return % (win% · PF · #trades) per asset
          </h3>
          <p className="text-[11px] text-gray-500 mb-3">
            Best return per asset is highlighted. Green = profitable, red = losing.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-gray-500 border-b border-gray-800">
                <tr>
                  <th className="text-left font-medium py-2 pr-3">Strategy</th>
                  {matrix.assets.map((a) => <th key={a} className="text-right font-medium py-2 px-3">{a}</th>)}
                </tr>
              </thead>
              <tbody>
                {matrix.strategies.map((st) => (
                  <tr key={st} className="border-b border-gray-900">
                    <td className="py-2 pr-3 font-mono text-gray-300">{st}</td>
                    {matrix.assets.map((a) => {
                      const c = matrix.grid[a]?.[st];
                      if (!c || c.error) return <td key={a} className="py-2 px-3 text-right text-gray-700">—</td>;
                      const best = bestStrategyFor(matrix, a);
                      const isBest = best === st;
                      return (
                        <td key={a} className={`py-2 px-3 text-right font-mono ${isBest ? "bg-emerald-950/30 rounded" : ""}`}>
                          <span className={pctColor(c.return_pct)}>{c.return_pct}%</span>
                          {isBest && <span className="text-emerald-500"> ★</span>}
                          <div className="text-[10px] text-gray-600">
                            {c.win_rate_pct}% · {c.profit_factor ?? "—"} · {c.trades}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Results ────────────────────────────────────────────── */}
      {m && (
        <>
          {/* Gross vs Net headline */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card title="Net Return (after costs)" big={`${m.total_return_pct}%`} color={pctColor(m.total_return_pct)} />
            <Card title="Gross Return (before costs)" big={`${m.gross_return_pct}%`} color={pctColor(m.gross_return_pct)} />
            <Card title="Final Balance" big={money(m.final_balance)} />
          </div>

          {/* Equity curve */}
          <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">
              Equity Curve (net)
            </h3>
            <EquityCurve data={res!.equity_curve} initial={form.initial_capital} />
          </div>

          {/* Commission breakdown — the point of this exercise */}
          <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">
              Brokerage Impact
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <Stat label="Gross Profit" value={money(m.gross_profit)} color={pctColor(m.gross_profit)} />
              <Stat label="Total Commission" value={`-${money(m.total_commission)}`} color="text-rose-400" />
              <Stat label="Net Profit" value={money(m.net_profit)} color={pctColor(m.net_profit)} />
              <Stat label="Commission Drag" value={`${m.commission_drag_pct}%`} color="text-amber-400" />
              <Stat label="Total Lots Traded" value={String(m.total_lots_traded)} />
              <Stat label="Avg Commission / Trade" value={money(m.avg_commission_per_trade)} />
              <Stat label="Commission / lot / side" value={money(res!.commission_per_lot_used)} />
            </div>
          </div>

          {/* Performance stats */}
          <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">
              Performance
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <Stat label="Trades" value={String(m.total_trades)} />
              <Stat label="Win Rate" value={`${m.win_rate_pct}%`} />
              <Stat label="Profit Factor" value={m.profit_factor === null ? "—" : String(m.profit_factor)} />
              <Stat label="Max Drawdown" value={`${m.max_drawdown_pct}%`} color="text-rose-400" />
              <Stat label="Sharpe" value={String(m.sharpe)} />
              <Stat label="Avg Win" value={money(m.avg_win)} color="text-emerald-400" />
              <Stat label="Avg Loss" value={money(m.avg_loss)} color="text-rose-400" />
            </div>
          </div>

          {/* Walk-forward */}
          {res!.walk_forward && (
            <div className="bg-[#0a0d12] border border-indigo-900/50 rounded-xl p-5">
              <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-400 mb-3">
                Walk-Forward (out-of-sample) — trust these, not the single run
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm mb-4">
                <Stat label="Mean OOS Return" value={`${res!.walk_forward.summary.mean_oos_return_pct}%`} color={pctColor(res!.walk_forward.summary.mean_oos_return_pct)} />
                <Stat label="Positive Folds" value={`${res!.walk_forward.summary.positive_folds}/${res!.walk_forward.summary.total_folds}`} />
                <Stat label="Consistency" value={`${(res!.walk_forward.summary.consistency * 100).toFixed(0)}%`} />
              </div>
              <table className="w-full text-xs">
                <thead className="text-gray-500 border-b border-gray-800">
                  <tr>
                    <Th>Fold</Th><Th>OOS Bars</Th><Th>Return</Th><Th>Win %</Th><Th>Max DD</Th><Th>Commission</Th>
                  </tr>
                </thead>
                <tbody>
                  {res!.walk_forward.folds.map((f) => (
                    <tr key={f.fold} className="border-b border-gray-900">
                      <Td>{f.fold}</Td>
                      <Td>{f.oos_bars}</Td>
                      <Td className={pctColor(f.oos_metrics.total_return_pct)}>{f.oos_metrics.total_return_pct}%</Td>
                      <Td>{f.oos_metrics.win_rate_pct}%</Td>
                      <Td className="text-rose-400">{f.oos_metrics.max_drawdown_pct}%</Td>
                      <Td>{money(f.oos_metrics.total_commission)}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Trades */}
          <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">
              Recent Trades (last {res!.trades.length})
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-gray-500 border-b border-gray-800">
                  <tr>
                    <Th>Time</Th><Th>Dir</Th><Th>Entry</Th><Th>Exit</Th><Th>Lots</Th>
                    <Th>Reason</Th><Th>Gross</Th><Th>Commission</Th><Th>Net</Th>
                  </tr>
                </thead>
                <tbody>
                  {res!.trades.map((t, i) => (
                    <tr key={i} className="border-b border-gray-900">
                      <Td className="text-gray-500">{t.time.slice(0, 16)}</Td>
                      <Td className={t.direction === "BUY" ? "text-emerald-400" : "text-rose-400"}>{t.direction}</Td>
                      <Td>{t.entry}</Td>
                      <Td>{t.exit}</Td>
                      <Td>{t.lots}</Td>
                      <Td className={t.reason === "TGT" ? "text-emerald-400" : "text-rose-400"}>{t.reason}</Td>
                      <Td className={pctColor(t.gross_pnl)}>{money(t.gross_pnl)}</Td>
                      <Td className="text-rose-400">-{money(t.commission)}</Td>
                      <Td className={pctColor(t.pnl)}>{money(t.pnl)}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function bestStrategyFor(m: MatrixResp, asset: string): string | null {
  let best: string | null = null;
  let bestVal = -Infinity;
  for (const st of m.strategies) {
    const c = m.grid[asset]?.[st];
    if (!c || c.error) continue;
    if (c.return_pct > bestVal) {
      bestVal = c.return_pct;
      best = st;
    }
  }
  return best;
}

/* ── tiny presentational helpers ──────────────────────────────── */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col space-y-1">
      <label className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</label>
      {children}
    </div>
  );
}

function Num({
  label, k, form, set, step = 1,
}: {
  label: string;
  k: keyof typeof DEFAULTS;
  form: typeof DEFAULTS;
  set: (k: keyof typeof DEFAULTS, v: number) => void;
  step?: number;
}) {
  return (
    <Field label={label}>
      <input
        type="number"
        step={step}
        value={form[k] as number}
        onChange={(e) => set(k, parseFloat(e.target.value) || 0)}
        className={`${INPUT} font-mono`}
      />
    </Field>
  );
}

function Card({ title, big, color = "text-white" }: { title: string; big: string; color?: string }) {
  return (
    <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
      <p className="text-[10px] text-gray-500 uppercase tracking-wider">{title}</p>
      <p className={`text-3xl font-mono mt-1 ${color}`}>{big}</p>
    </div>
  );
}

function Stat({ label, value, color = "text-gray-200" }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <p className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</p>
      <p className={`font-mono mt-0.5 ${color}`}>{value}</p>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="text-left font-medium py-2 px-2">{children}</th>;
}
function Td({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <td className={`py-1.5 px-2 font-mono ${className}`}>{children}</td>;
}
