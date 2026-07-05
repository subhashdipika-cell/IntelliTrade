"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { DecisionTree, type Decision } from "@/components/DecisionTree";
import { ScannerPanel } from "@/components/ScannerPanel";

interface RunResult {
  asset: string;
  blocked: boolean;
  blocked_by: string | null;
  ticket: number | null;
  signal: {
    direction: string;
    entry: number;
    sl: number;
    tp: number;
    lots: number;
  } | null;
  decision_tree: Decision[];
}

interface Monitored {
  count: number;
  trades: { ticket: number; asset: string; direction: string | null; entry: number | null }[];
}

interface ActiveSettings {
  base_lots: number;
  lots_by_asset: Record<string, number>;
  max_daily_loss_pct: number;
  hard_stop_override: boolean;
  rr_ratio: string;
}

const DEFAULTS = {
  asset: "GOLD",
  timeframe: "H1",
  strategy: "sma_crossover",
  wiki_enabled: true,
  daily_loss_pct: 0.0,
};

const INPUT =
  "bg-[#0d1117] border border-gray-700 rounded px-2 py-2 text-xs w-full outline-none focus:border-amber-600";

export default function LivePage() {
  const [form, setForm] = useState(DEFAULTS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [res, setRes] = useState<RunResult | null>(null);
  const [monitored, setMonitored] = useState<Monitored | null>(null);
  const [active, setActive] = useState<ActiveSettings | null>(null);

  const set = (k: keyof typeof DEFAULTS, v: number | string | boolean) =>
    setForm((f) => ({ ...f, [k]: v }));

  const loadMonitored = useCallback(() => {
    api.monitored().then((d) => setMonitored(d as Monitored)).catch(() => setMonitored(null));
  }, []);

  const loadActive = useCallback(() => {
    api
      .moneyOverview()
      .then((d) => setActive((d as { settings: ActiveSettings }).settings))
      .catch(() => setActive(null));
  }, []);

  useEffect(() => {
    loadMonitored();
    loadActive();
    const id = setInterval(loadMonitored, 15000);
    return () => clearInterval(id);
  }, [loadMonitored, loadActive]);

  async function run() {
    setLoading(true);
    setError("");
    setRes(null);
    try {
      const data = (await api.runPipeline(form)) as RunResult;
      setRes(data);
      loadMonitored();
      loadActive();
    } catch {
      setError("Request failed — is the backend running on :8100?");
    } finally {
      setLoading(false);
    }
  }

  async function testTrade() {
    if (!confirm(`Place a real DEMO test order: BUY ${form.asset} (min lot, tight bracket)?`)) return;
    setLoading(true);
    setError("");
    setRes(null);
    try {
      const d = (await api.testTrade({ asset: form.asset, direction: "BUY" })) as {
        status: string;
        ticket: number | null;
        signal: RunResult["signal"];
        decision_tree: Decision[];
      };
      setRes({
        asset: form.asset,
        blocked: d.status === "BLOCKED",
        blocked_by: d.status === "BLOCKED" ? "test-trade guard" : null,
        ticket: d.ticket,
        signal: d.signal,
        decision_tree: d.decision_tree,
      });
      loadMonitored();
    } catch {
      setError("Test trade request failed — is the backend running on :8100?");
    } finally {
      setLoading(false);
    }
  }

  const sig = res?.signal;

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <h2 className="text-2xl font-bold">Live — Run Signal Through Pipeline</h2>

      <ScannerPanel />

      {/* ── Controls ───────────────────────────────────────────── */}
      <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Field label="Asset">
            <select value={form.asset} onChange={(e) => set("asset", e.target.value)} className={INPUT}>
              <option>GOLD</option>
              <option>BTC</option>
              <option>ETH</option>
            </select>
          </Field>
          <Field label="Timeframe">
            <select value={form.timeframe} onChange={(e) => set("timeframe", e.target.value)} className={INPUT}>
              {["M15", "M30", "H1", "H4", "D1"].map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </Field>
          <Field label="Strategy">
            <select value={form.strategy} onChange={(e) => set("strategy", e.target.value)} className={INPUT}>
              <option value="sma_crossover">SMA Crossover</option>
              <option value="donchian_breakout">Donchian Breakout</option>
            </select>
          </Field>
          <Field label="Today's Loss % (sim)">
            <input
              type="number"
              step={0.5}
              value={form.daily_loss_pct}
              onChange={(e) => set("daily_loss_pct", parseFloat(e.target.value) || 0)}
              className={`${INPUT} font-mono`}
            />
          </Field>
        </div>

        {/* Active risk settings — owned by Money Mgmt, shown read-only here */}
        {active && (
          <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-1 text-xs text-gray-400 bg-[#0d1117] border border-gray-800 rounded-lg px-4 py-3">
            <span className="text-[10px] uppercase tracking-wider text-gray-500">Active risk (from Money Mgmt):</span>
            <span>{form.asset} Lots <span className="text-gray-200 font-mono">{active.lots_by_asset?.[form.asset] ?? active.base_lots}</span></span>
            <span>Max daily loss <span className="text-gray-200 font-mono">{active.max_daily_loss_pct}%</span></span>
            <span>R:R <span className="text-gray-200 font-mono">{active.rr_ratio}</span></span>
            <span>
              Hard-stop override{" "}
              <span className={active.hard_stop_override ? "text-rose-400 font-semibold" : "text-emerald-400"}>
                {active.hard_stop_override ? "ON ⚠" : "off"}
              </span>
            </span>
          </div>
        )}

        <div className="flex items-center gap-6 mt-4 flex-wrap">
          <Toggle
            label="Obsidian Wiki screening"
            on={form.wiki_enabled}
            onChange={(v) => set("wiki_enabled", v)}
            color="bg-purple-600"
          />
          <button
            onClick={testTrade}
            disabled={loading}
            title="Places a real minimum-lot order on the DEMO account to exercise the full loop"
            className="ml-auto px-5 py-2 border border-rose-700 text-rose-300 hover:bg-rose-950/40 disabled:opacity-50 rounded-lg text-sm font-semibold"
          >
            Place DEMO Test Trade
          </button>
          <button
            onClick={run}
            disabled={loading}
            className="px-6 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 rounded-lg text-sm font-bold"
          >
            {loading ? "Running…" : "Run Signal"}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-rose-950/40 border border-rose-900/50 text-rose-300 text-sm rounded-lg p-4">
          {error}
        </div>
      )}

      {/* ── Result ─────────────────────────────────────────────── */}
      {res && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Outcome + signal */}
          <div className="space-y-4">
            <div
              className={`rounded-xl p-5 border ${
                res.blocked
                  ? "bg-rose-950/30 border-rose-900/50"
                  : sig
                    ? "bg-emerald-950/30 border-emerald-900/50"
                    : "bg-gray-900 border-gray-800"
              }`}
            >
              <p className="text-[10px] uppercase tracking-wider text-gray-500">Outcome</p>
              <p className="text-xl font-bold mt-1">
                {res.blocked ? (
                  <span className="text-rose-400">BLOCKED at “{res.blocked_by}”</span>
                ) : res.ticket !== null ? (
                  <span className="text-emerald-400">EXECUTED (ticket {res.ticket})</span>
                ) : sig ? (
                  <span className="text-amber-400">PASSED (no broker ticket — stub)</span>
                ) : (
                  <span className="text-gray-400">No setup this bar</span>
                )}
              </p>
            </div>

            {sig && (
              <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
                <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-3">Signal</p>
                <div className="grid grid-cols-2 gap-3 text-sm font-mono">
                  <KV k="Direction" v={sig.direction} color={sig.direction === "BUY" ? "text-emerald-400" : "text-rose-400"} />
                  <KV k="Lots" v={String(sig.lots)} />
                  <KV k="Entry" v={String(sig.entry)} />
                  <KV k="Stop Loss" v={String(sig.sl)} />
                  <KV k="Target" v={String(sig.tp)} />
                </div>
              </div>
            )}
          </div>

          {/* Decision tree */}
          <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-4">
              Decision Tree — why {res.asset} {res.blocked ? "was blocked" : "passed"}
            </h3>
            <DecisionTree decisions={res.decision_tree} />
          </div>
        </div>
      )}

      {/* ── Monitored open trades ──────────────────────────────── */}
      <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
        <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">
          Monitor Queue — open trades watched for exit alerts ({monitored?.count ?? 0})
        </h3>
        {monitored && monitored.count > 0 ? (
          <table className="w-full text-xs">
            <thead className="text-gray-500 border-b border-gray-800">
              <tr>
                <th className="text-left font-medium py-2 px-2">Ticket</th>
                <th className="text-left font-medium py-2 px-2">Asset</th>
                <th className="text-left font-medium py-2 px-2">Dir</th>
                <th className="text-left font-medium py-2 px-2">Entry</th>
              </tr>
            </thead>
            <tbody>
              {monitored.trades.map((t) => (
                <tr key={t.ticket} className="border-b border-gray-900 font-mono">
                  <td className="py-1.5 px-2">{t.ticket}</td>
                  <td className="py-1.5 px-2">{t.asset}</td>
                  <td className={`py-1.5 px-2 ${t.direction === "BUY" ? "text-emerald-400" : "text-rose-400"}`}>
                    {t.direction}
                  </td>
                  <td className="py-1.5 px-2">{t.entry}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-xs text-gray-500">
            No open trades. Executed trades appear here until the monitor detects their close.
          </p>
        )}
      </div>
    </div>
  );
}

/* ── helpers ──────────────────────────────────────────────────── */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col space-y-1">
      <label className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</label>
      {children}
    </div>
  );
}

function KV({ k, v, color = "text-gray-200" }: { k: string; v: string; color?: string }) {
  return (
    <div>
      <span className="text-gray-500">{k}: </span>
      <span className={color}>{v}</span>
    </div>
  );
}

function Toggle({
  label, on, onChange, color, warn,
}: {
  label: string;
  on: boolean;
  onChange: (v: boolean) => void;
  color: string;
  warn?: string;
}) {
  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-2">
        <button
          onClick={() => onChange(!on)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
            on ? color : "bg-gray-700"
          }`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
              on ? "translate-x-6" : "translate-x-1"
            }`}
          />
        </button>
        <span className="text-xs text-gray-300">{label}</span>
      </div>
      {warn && <span className="text-[10px] text-rose-400 mt-1">⚠ {warn}</span>}
    </div>
  );
}
