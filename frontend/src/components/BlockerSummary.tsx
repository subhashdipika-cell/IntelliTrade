"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

interface BlockedDecision {
  evaluated_at: string;
  bar_time: string;
  asset: string;
  timeframe: string;
  strategy: string | null;
  blocked_by: string | null;
  reason: string;
  ai_score: number | null;
  signal: { direction: string } | null;
}

interface BlockerData {
  hours: number;
  evaluations: number;
  blocked: number;
  passed: number;
  by_stage: Record<string, number>;
  by_strategy: Record<string, number>;
  latest: BlockedDecision[];
}

const STAGE_LABELS: Record<string, string> = {
  market: "Market data",
  strategy: "No strategy setup",
  ai_filter: "AI confidence",
  wiki_filter: "Wiki filter",
  risk: "Risk controls",
  scanner_guard: "Scanner guard",
  execution: "Broker execution",
};

const STAGE_COLORS: Record<string, string> = {
  strategy: "bg-amber-500",
  ai_filter: "bg-violet-500",
  risk: "bg-rose-500",
  scanner_guard: "bg-sky-500",
  execution: "bg-red-500",
};

export function BlockerSummary() {
  const [data, setData] = useState<BlockerData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    api
      .scannerBlockers(24)
      .then((result) => {
        setData(result as BlockerData);
        setError("");
      })
      .catch(() => setError("Blocker journal unavailable. Restart the backend to activate it."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [load]);

  const stageRows = Object.entries(data?.by_stage ?? {}).sort((a, b) => b[1] - a[1]);
  const strategyRows = Object.entries(data?.by_strategy ?? {}).sort((a, b) => b[1] - a[1]);
  const maxStage = Math.max(1, ...stageRows.map(([, count]) => count));

  return (
    <section className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h3 className="text-sm font-bold text-gray-200">Signal Blockers</h3>
          <p className="text-xs text-gray-500">
            Every deployed strategy decision from completed candles · last 24 hours
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="px-3 py-1.5 text-xs border border-gray-700 rounded-md text-gray-400 hover:text-white hover:border-gray-500 disabled:opacity-50"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {error && <p className="text-xs text-rose-400">{error}</p>}

      {!error && data && (
        <>
          <div className="grid grid-cols-3 gap-3 mb-5">
            <Metric label="Evaluated" value={data.evaluations} color="text-gray-200" />
            <Metric label="Blocked" value={data.blocked} color="text-amber-400" />
            <Metric label="Passed" value={data.passed} color="text-emerald-400" />
          </div>

          {data.evaluations === 0 ? (
            <div className="rounded-lg border border-dashed border-gray-700 p-5 text-center">
              <p className="text-sm text-gray-300">Waiting for the next completed candle.</p>
              <p className="text-xs text-gray-500 mt-1">
                The journal begins filling after the restarted scanner evaluates its next new bar.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <div>
                <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">Blocked by stage</p>
                <div className="space-y-2">
                  {stageRows.length === 0 && <p className="text-xs text-emerald-400">No blocks recorded.</p>}
                  {stageRows.map(([stage, count]) => (
                    <div key={stage}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-gray-300">{STAGE_LABELS[stage] ?? stage}</span>
                        <span className="font-mono text-gray-400">{count}</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-gray-800 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${STAGE_COLORS[stage] ?? "bg-gray-500"}`}
                          style={{ width: `${Math.max(5, (count / maxStage) * 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>

                {strategyRows.length > 0 && (
                  <div className="mt-5">
                    <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">Most blocked strategies</p>
                    <div className="flex flex-wrap gap-2">
                      {strategyRows.slice(0, 6).map(([strategy, count]) => (
                        <span key={strategy} className="text-[11px] px-2 py-1 rounded border border-gray-700 text-gray-400">
                          {strategy} <strong className="text-gray-200">{count}</strong>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div>
                <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">Latest blocked decisions</p>
                <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                  {data.latest.slice(0, 10).map((row, index) => (
                    <div key={`${row.evaluated_at}-${index}`} className="bg-[#0d1117] border border-gray-800 rounded-lg p-3">
                      <div className="flex items-center justify-between gap-2 text-[11px]">
                        <span className="font-semibold text-gray-200">
                          {row.asset} · {row.timeframe} · {row.strategy ?? "Unknown strategy"}
                        </span>
                        <span className="text-gray-600 whitespace-nowrap">{formatTime(row.evaluated_at)}</span>
                      </div>
                      <p className="text-[11px] text-gray-400 mt-1 leading-relaxed">{row.reason}</p>
                      <div className="flex gap-2 mt-1.5 text-[10px]">
                        <span className="text-amber-400">{STAGE_LABELS[row.blocked_by ?? ""] ?? row.blocked_by}</span>
                        {row.ai_score != null && (
                          <span className="text-violet-400">AI {(row.ai_score * 100).toFixed(0)}%</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function Metric({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="bg-[#0d1117] border border-gray-800 rounded-lg px-3 py-2.5">
      <p className="text-[10px] uppercase tracking-wider text-gray-500">{label}</p>
      <p className={`text-xl font-bold font-mono ${color}`}>{value}</p>
    </div>
  );
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
  });
}
