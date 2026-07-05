"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

interface Metrics {
  trades: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  net_pnl: number;
  gross_profit: number;
  gross_loss: number;
  profit_factor: number | null;
  expectancy: number;
  avg_win: number;
  avg_loss: number;
  payoff_ratio: number | null;
  avg_planned_rr: number | null;
  best_trade: number;
  worst_trade: number;
  max_drawdown: number;
  max_win_streak: number;
  max_loss_streak: number;
  by_outcome: Record<string, number>;
}
interface Report {
  month: string;
  trades?: number;
  message?: string;
  overall?: Metrics;
  by_strategy?: Record<string, Metrics>;
  ranking?: string[];
}

const money = (v: number) => `$${v.toFixed(2)}`;
const pc = (v: number) => (v >= 0 ? "text-emerald-400" : "text-rose-400");
const num = (v: number | null) => (v === null ? "—" : String(v));
const thisMonth = () => new Date().toISOString().slice(0, 7);

export function MonthlyReport() {
  const [month, setMonth] = useState(thisMonth());
  const [r, setR] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);

  const load = useCallback((m: string) => {
    setLoading(true);
    api
      .monthlyReport(m)
      .then((d) => setR(d as Report))
      .catch(() => setR(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load(month);
  }, [month, load]);

  const o = r?.overall;

  return (
    <div className="bg-[#0a0d12] border border-indigo-900/50 rounded-xl p-5">
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <div>
          <h3 className="text-sm font-bold text-indigo-400">Monthly Report</h3>
          <p className="text-xs text-gray-500">Per-strategy performance — pick a month to analyse.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="bg-[#0d1117] border border-gray-700 rounded px-3 py-1.5 text-sm outline-none focus:border-indigo-600"
          />
          <button
            onClick={async () => {
              setExportMsg("Exporting…");
              try {
                const d = (await api.exportMonthly(month)) as {
                  status: string; path?: string; trades?: number; message?: string;
                };
                setExportMsg(
                  d.status === "SUCCESS"
                    ? `✓ ${d.trades} trades → ${d.path}`
                    : `✗ ${d.message ?? d.status}`,
                );
              } catch {
                setExportMsg("✗ export failed (backend running?)");
              }
            }}
            className="bg-emerald-900/40 border border-emerald-700/50 text-emerald-300 rounded px-3 py-1.5 text-sm hover:bg-emerald-900/60"
          >
            Export → Obsidian
          </button>
        </div>
      </div>

      {exportMsg && (
        <p className="text-xs text-gray-400 mb-2">
          Obsidian export: {exportMsg}
        </p>
      )}

      {loading && <p className="text-xs text-gray-500">Loading…</p>}

      {!loading && r && r.trades === 0 && (
        <p className="text-xs text-gray-500">{r.message ?? "No closed trades this month."}</p>
      )}

      {!loading && o && (
        <>
          {/* Overall headline */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-5">
            <Stat label="Trades" value={String(o.trades)} />
            <Stat label="Win Rate" value={`${o.win_rate_pct}%`} />
            <Stat label="Net P/L" value={money(o.net_pnl)} color={pc(o.net_pnl)} />
            <Stat label="Profit Factor" value={num(o.profit_factor)} />
            <Stat label="Realised R:R" value={num(o.payoff_ratio)} />
            <Stat label="Planned R:R" value={num(o.avg_planned_rr)} />
            <Stat label="Expectancy / trade" value={money(o.expectancy)} color={pc(o.expectancy)} />
            <Stat label="Best Trade" value={money(o.best_trade)} color="text-emerald-400" />
            <Stat label="Worst Trade" value={money(o.worst_trade)} color="text-rose-400" />
            <Stat label="Max Drawdown" value={money(o.max_drawdown)} color="text-rose-400" />
            <Stat label="Max Loss Streak" value={String(o.max_loss_streak)} />
            <Stat label="Max Win Streak" value={String(o.max_win_streak)} />
          </div>

          {/* Per-strategy table (ranked best → worst by net P/L) */}
          <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">
            By Strategy — ranked best → worst
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-gray-500 border-b border-gray-800">
                <tr>
                  <Th left>Strategy</Th>
                  <Th>Trades</Th><Th>Win %</Th><Th>Net P/L</Th><Th>PF</Th>
                  <Th>Realised R:R</Th><Th>Planned R:R</Th>
                  <Th>Best</Th><Th>Worst</Th><Th>Max DD</Th><Th>Outcomes</Th>
                </tr>
              </thead>
              <tbody>
                {(r.ranking ?? []).map((st, i) => {
                  const m = r.by_strategy![st];
                  const oc = m.by_outcome;
                  return (
                    <tr key={st} className={`border-b border-gray-900 font-mono ${i === 0 && m.net_pnl > 0 ? "bg-emerald-950/20" : ""}`}>
                      <td className="py-1.5 px-2 text-left text-gray-200">
                        {i === 0 && m.net_pnl > 0 ? "★ " : ""}{st}
                      </td>
                      <Td>{m.trades}</Td>
                      <Td>{m.win_rate_pct}%</Td>
                      <Td className={pc(m.net_pnl)}>{money(m.net_pnl)}</Td>
                      <Td>{num(m.profit_factor)}</Td>
                      <Td>{num(m.payoff_ratio)}</Td>
                      <Td>{num(m.avg_planned_rr)}</Td>
                      <Td className="text-emerald-400">{money(m.best_trade)}</Td>
                      <Td className="text-rose-400">{money(m.worst_trade)}</Td>
                      <Td className="text-rose-400">{money(m.max_drawdown)}</Td>
                      <Td className="text-gray-500">
                        {Object.entries(oc).map(([k, v]) => `${k}:${v}`).join(" ")}
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] text-gray-600 mt-2">
            Realised R:R = avg win ÷ avg loss · Planned R:R = avg target/stop distance · PF = gross profit ÷ gross loss.
          </p>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, color = "text-gray-200" }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-[#0d1117] border border-gray-800 rounded-lg px-3 py-2">
      <p className="text-[9px] text-gray-500 uppercase tracking-wider">{label}</p>
      <p className={`font-mono text-sm mt-0.5 ${color}`}>{value}</p>
    </div>
  );
}
function Th({ children, left }: { children: React.ReactNode; left?: boolean }) {
  return <th className={`font-medium py-2 px-2 ${left ? "text-left" : "text-right"}`}>{children}</th>;
}
function Td({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <td className={`py-1.5 px-2 text-right ${className}`}>{children}</td>;
}
