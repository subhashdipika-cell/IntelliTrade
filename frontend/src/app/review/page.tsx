"use client";

import { useState } from "react";
import { api } from "@/lib/api";

interface Metrics {
  trades: number;
  wins?: number;
  losses?: number;
  win_rate_pct?: number;
  net_pnl?: number;
  profit_factor?: number | null;
  expectancy?: number;
  avg_planned_rr?: number | null;
  payoff_ratio?: number | null;
  max_drawdown?: number;
  by_outcome?: Record<string, number>;
}
interface Suggestion {
  strategy: string;
  asset: string;
  observation: string;
  action: string;
  confidence: string;
}
interface Review {
  generated_at: string;
  provider: string;
  model: string;
  total_trades: number;
  attributed_strategies: string[];
  unattributed_trades: number;
  stats: Record<string, Metrics>;
  summary: string | null;
  suggestions: Suggestion[];
  note?: string;
  raw?: string;
}

const num = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined ? "—" : v.toFixed(d);

const CONF: Record<string, string> = {
  high: "bg-emerald-900/40 text-emerald-300 border-emerald-800",
  medium: "bg-amber-900/40 text-amber-300 border-amber-800",
  low: "bg-gray-800 text-gray-400 border-gray-700",
};

export default function ReviewPage() {
  const [data, setData] = useState<Review | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  async function run() {
    setLoading(true);
    setErr("");
    try {
      setData((await api.strategyReview()) as Review);
    } catch {
      setErr("Request failed — is the backend running on :8100?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-bold">Strategy Review</h2>
          <p className="text-sm text-gray-500 mt-1">
            An LLM reads your real closed-trade performance and suggests concrete refinements.
            Advisory only — nothing is changed automatically.
          </p>
        </div>
        <button
          onClick={run}
          disabled={loading}
          className="px-5 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 rounded-lg text-sm font-bold whitespace-nowrap"
        >
          {loading ? "Analyzing…" : "Run Review"}
        </button>
      </div>

      {loading && (
        <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-6 text-sm text-gray-400">
          Crunching your history through the model… a local Ollama model can take 30–90s on first run.
        </div>
      )}
      {err && (
        <div className="bg-rose-950/30 border border-rose-900/50 text-rose-300 text-sm rounded-lg p-4">{err}</div>
      )}

      {data && !loading && (
        <>
          {/* Meta */}
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-xs text-gray-400 bg-[#0d1117] border border-gray-800 rounded-lg px-4 py-3">
            <span>Model <span className="text-gray-200 font-mono">{data.provider}/{data.model}</span></span>
            <span>Trades analysed <span className="text-gray-200 font-mono">{data.total_trades - data.unattributed_trades}</span></span>
            <span>Strategies <span className="text-gray-200 font-mono">{data.attributed_strategies.join(", ") || "none"}</span></span>
            {data.unattributed_trades > 0 && (
              <span className="text-gray-500">({data.unattributed_trades} unattributed excluded)</span>
            )}
          </div>

          {data.note && (
            <div className="bg-amber-950/30 border border-amber-900/50 text-amber-200 text-sm rounded-lg p-4">
              {data.note}
            </div>
          )}

          {data.summary && (
            <div className="bg-[#0a0d12] border border-amber-900/40 rounded-xl p-5">
              <p className="text-[10px] uppercase tracking-wider text-amber-500 mb-1">Overall read</p>
              <p className="text-sm text-gray-200">{data.summary}</p>
            </div>
          )}

          {/* Suggestions */}
          {data.suggestions.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-lg font-semibold text-amber-500">Suggestions</h3>
              {data.suggestions.map((s, i) => (
                <div key={i} className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
                  <div className="flex items-center gap-2 flex-wrap mb-2">
                    <span className="text-sm font-bold text-white">{s.strategy}</span>
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-gray-800 text-gray-300">{s.asset}</span>
                    <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border ${CONF[String(s.confidence).toLowerCase()] ?? CONF.low}`}>
                      {s.confidence}
                    </span>
                  </div>
                  <p className="text-xs text-gray-400 mb-1"><span className="text-gray-500">Observed:</span> {s.observation}</p>
                  <p className="text-sm text-emerald-300">→ {s.action}</p>
                </div>
              ))}
            </div>
          )}

          {data.raw && (
            <pre className="bg-[#0d1117] border border-gray-800 rounded-lg p-4 text-xs text-gray-400 overflow-x-auto whitespace-pre-wrap">{data.raw}</pre>
          )}

          {/* Stats table */}
          {Object.keys(data.stats).length > 0 && (
            <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5 overflow-x-auto">
              <h3 className="text-lg font-semibold mb-3">Performance the model saw</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[10px] uppercase tracking-wider text-gray-500 text-left border-b border-gray-800">
                    <th className="py-2 pr-4">Strategy</th>
                    <th className="py-2 pr-4">Trades</th>
                    <th className="py-2 pr-4">Win%</th>
                    <th className="py-2 pr-4">Net P/L</th>
                    <th className="py-2 pr-4">PF</th>
                    <th className="py-2 pr-4">Expectancy</th>
                    <th className="py-2 pr-4">Planned R:R</th>
                    <th className="py-2 pr-4">Outcomes</th>
                  </tr>
                </thead>
                <tbody className="font-mono">
                  {Object.entries(data.stats).map(([name, m]) => (
                    <tr key={name} className="border-b border-gray-900">
                      <td className="py-2 pr-4 font-sans text-gray-200">{name}</td>
                      <td className="py-2 pr-4">{m.trades}</td>
                      <td className="py-2 pr-4">{num(m.win_rate_pct, 0)}%</td>
                      <td className={`py-2 pr-4 ${(m.net_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{num(m.net_pnl)}</td>
                      <td className="py-2 pr-4">{num(m.profit_factor)}</td>
                      <td className="py-2 pr-4">{num(m.expectancy)}</td>
                      <td className="py-2 pr-4">{num(m.avg_planned_rr)}</td>
                      <td className="py-2 pr-4 text-gray-400">
                        {m.by_outcome ? Object.entries(m.by_outcome).map(([k, v]) => `${k}:${v}`).join(" ") : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {!data && !loading && !err && (
        <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-8 text-center text-gray-500 text-sm">
          Click <span className="text-amber-500 font-semibold">Run Review</span> to analyse your strategies&apos; live performance.
        </div>
      )}
    </div>
  );
}
