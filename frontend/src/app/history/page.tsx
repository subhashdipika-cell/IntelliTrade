"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { DecisionTree, type Decision } from "@/components/DecisionTree";
import { MonthlyReport } from "@/components/MonthlyReport";

interface Trade {
  ticket: number | null;
  asset: string;
  strategy: string | null;
  direction: string | null;
  entry: number | null;
  sl: number | null;
  tp: number | null;
  lots: number | null;
  close_price: number;
  outcome: string;
  pnl: number;
  final_capital: number | null;
  opened_at: string | null;
  closed_at: string;
  decision_tree: Decision[];
}

interface Summary {
  month: string;
  trades: number;
  message?: string;
  total_pnl?: number;
  win_rate_pct?: number;
  by_outcome?: Record<string, number>;
  by_asset?: Record<string, { count: number; pnl: number; win_rate_pct: number }>;
  ending_capital?: number | null;
}

const money = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `$${v.toFixed(2)}`;
const pc = (v: number) => (v >= 0 ? "text-emerald-400" : "text-rose-400");

const OUTCOME_STYLE: Record<string, string> = {
  TGT: "text-emerald-400",
  SL: "text-rose-400",
  TSL: "text-amber-400",
  MANUAL: "text-gray-400",
};

interface Cell {
  count: number;
  pnl: number;
  win_rate_pct: number;
}
interface Matrix {
  trades: number;
  strategies?: string[];
  assets?: string[];
  matrix?: Record<string, Record<string, Cell>>;
  totals?: Record<string, Cell>;
}

export default function HistoryPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [sm, setSm] = useState<Matrix | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    api
      .historyTrades()
      .then((d) => setTrades((d as { trades: Trade[] }).trades))
      .catch(() => setErr("Backend unreachable — start it on :8100."));
    api
      .historySummary()
      .then((d) => setSummary(d as Summary))
      .catch(() => setSummary(null));
    api
      .strategyMatrix()
      .then((d) => setSm(d as Matrix))
      .catch(() => setSm(null));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="p-6 space-y-6 max-w-6xl">
      <h2 className="text-2xl font-bold">History</h2>

      {err && (
        <div className="bg-rose-950/40 border border-rose-900/50 text-rose-300 text-sm rounded-lg p-4">
          {err}
        </div>
      )}

      <MonthlyReport />

      {/* Strategy × Asset scoreboard (live closed trades) */}
      {sm && sm.trades > 0 && sm.matrix && sm.strategies && sm.assets && (
        <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
          <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-1">
            Strategy × Asset — net P/L from live closed trades
          </h3>
          <p className="text-[11px] text-gray-500 mb-3">
            Each cell: net P/L · win% · #trades. Green = working, red = not.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-gray-500 border-b border-gray-800">
                <tr>
                  <th className="text-left font-medium py-2 pr-3">Strategy</th>
                  {sm.assets.map((a) => <th key={a} className="text-right font-medium py-2 px-2">{a}</th>)}
                  <th className="text-right font-medium py-2 pl-3">Total</th>
                </tr>
              </thead>
              <tbody>
                {sm.strategies.map((st) => (
                  <tr key={st} className="border-b border-gray-900">
                    <td className="py-2 pr-3 font-mono text-gray-300">{st}</td>
                    {sm.assets!.map((a) => {
                      const c = sm.matrix![st]?.[a];
                      return (
                        <td key={a} className="py-2 px-2 text-right font-mono">
                          {c && c.count > 0 ? (
                            <>
                              <span className={pc(c.pnl)}>{money(c.pnl)}</span>
                              <span className="text-gray-600"> · {c.win_rate_pct}% · {c.count}</span>
                            </>
                          ) : <span className="text-gray-700">—</span>}
                        </td>
                      );
                    })}
                    <td className="py-2 pl-3 text-right font-mono">
                      <span className={pc(sm.totals?.[st]?.pnl ?? 0)}>{money(sm.totals?.[st]?.pnl ?? 0)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Monthly summary */}
      {summary && summary.trades > 0 ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card title={`Trades (${summary.month})`} value={String(summary.trades)} />
            <Card title="Total P/L" value={money(summary.total_pnl)} color={pc(summary.total_pnl ?? 0)} />
            <Card title="Win Rate" value={`${summary.win_rate_pct}%`} />
            <Card title="Ending Capital" value={money(summary.ending_capital)} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {/* Outcome distribution */}
            <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
              <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-3">Outcomes</p>
              <div className="flex gap-3 flex-wrap">
                {Object.entries(summary.by_outcome ?? {}).map(([k, n]) => (
                  <div key={k} className="bg-[#0d1117] border border-gray-800 rounded-lg px-4 py-2">
                    <span className={`text-lg font-mono font-bold ${OUTCOME_STYLE[k] ?? "text-gray-300"}`}>{n}</span>
                    <span className="text-xs text-gray-500 ml-2">{k}</span>
                  </div>
                ))}
              </div>
            </div>
            {/* By asset */}
            <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
              <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">By Asset</p>
              <table className="w-full text-xs">
                <thead className="text-gray-500 border-b border-gray-800">
                  <tr>
                    <th className="text-left font-medium py-1.5">Asset</th>
                    <th className="text-right font-medium py-1.5">Trades</th>
                    <th className="text-right font-medium py-1.5">Win %</th>
                    <th className="text-right font-medium py-1.5">P/L</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(summary.by_asset ?? {}).map(([k, g]) => (
                    <tr key={k} className="border-b border-gray-900 font-mono">
                      <td className="py-1.5">{k}</td>
                      <td className="py-1.5 text-right">{g.count}</td>
                      <td className="py-1.5 text-right">{g.win_rate_pct}%</td>
                      <td className={`py-1.5 text-right ${pc(g.pnl)}`}>{money(g.pnl)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-6 text-sm text-gray-400">
          No closed trades recorded yet. When the monitor detects a position close, it stores the
          trade and its decision tree here.
        </div>
      )}

      {/* Trade log with expandable decision trees */}
      {trades.length > 0 && (
        <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
          <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-3">
            Closed Trades — click a row for its decision tree
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-gray-500 border-b border-gray-800">
                <tr>
                  <th className="text-left font-medium py-2 px-2">Closed</th>
                  <th className="text-left font-medium py-2 px-2">Ticket</th>
                  <th className="text-left font-medium py-2 px-2">Asset</th>
                  <th className="text-left font-medium py-2 px-2">Strategy</th>
                  <th className="text-left font-medium py-2 px-2">Dir</th>
                  <th className="text-right font-medium py-2 px-2">Entry</th>
                  <th className="text-right font-medium py-2 px-2">Close</th>
                  <th className="text-center font-medium py-2 px-2">Outcome</th>
                  <th className="text-right font-medium py-2 px-2">P/L</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t, i) => (
                  <Fragment key={i}>
                    <tr
                      onClick={() => setOpen(open === i ? null : i)}
                      className="border-b border-gray-900 font-mono cursor-pointer hover:bg-gray-900/50"
                    >
                      <td className="py-1.5 px-2 text-gray-500">{t.closed_at.slice(0, 16).replace("T", " ")}</td>
                      <td className="py-1.5 px-2">{t.ticket ?? "—"}</td>
                      <td className="py-1.5 px-2">{t.asset}</td>
                      <td className="py-1.5 px-2 text-gray-400">{t.strategy ?? "—"}</td>
                      <td className={`py-1.5 px-2 ${t.direction === "BUY" ? "text-emerald-400" : "text-rose-400"}`}>
                        {t.direction ?? "—"}
                      </td>
                      <td className="py-1.5 px-2 text-right">{t.entry ?? "—"}</td>
                      <td className="py-1.5 px-2 text-right">{t.close_price}</td>
                      <td className={`py-1.5 px-2 text-center font-bold ${OUTCOME_STYLE[t.outcome] ?? "text-gray-300"}`}>
                        {t.outcome}
                      </td>
                      <td className={`py-1.5 px-2 text-right font-bold ${pc(t.pnl)}`}>
                        {t.pnl >= 0 ? "+" : ""}{t.pnl.toFixed(2)}
                      </td>
                    </tr>
                    {open === i && (
                      <tr className="bg-[#0d1117]">
                        <td colSpan={9} className="px-4 py-4">
                          <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-3">
                            Why {t.asset} was traded
                          </p>
                          <DecisionTree decisions={t.decision_tree} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function Card({ title, value, color = "text-white" }: { title: string; value: string; color?: string }) {
  return (
    <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
      <p className="text-[10px] text-gray-500 uppercase tracking-wider">{title}</p>
      <p className={`text-2xl font-mono mt-1 ${color}`}>{value}</p>
    </div>
  );
}
