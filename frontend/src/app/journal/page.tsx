"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

interface Entry {
  file: string;
  date: string;
  asset: string;
  session: string;
  pnl: number;
  tags: string[];
  notes: string;
}

interface GroupStat {
  count: number;
  pnl: number;
  win_rate_pct: number;
}
interface Analysis {
  month: string;
  entries: number;
  message?: string;
  total_pnl?: number;
  avg_pnl?: number;
  win_rate_pct?: number;
  by_asset?: Record<string, GroupStat>;
  by_session?: Record<string, GroupStat>;
  tags?: { tag: string; count: number; pnl: number }[];
  best?: { date: string; asset: string; pnl: number };
  worst?: { date: string; asset: string; pnl: number };
  insights?: string[];
}

const INPUT =
  "bg-[#0d1117] border border-gray-700 rounded px-2 py-2 text-sm w-full outline-none focus:border-amber-600";
const today = () => new Date().toISOString().slice(0, 10);
const money = (v: number) => `$${v.toFixed(2)}`;
const pc = (v: number) => (v >= 0 ? "text-emerald-400" : "text-rose-400");

export default function JournalPage() {
  const [form, setForm] = useState({
    date: today(),
    asset: "XAUUSD+",
    session: "New York",
    pnl: 0,
    tags: "",
    notes: "",
  });
  const [entries, setEntries] = useState<Entry[]>([]);
  const [msg, setMsg] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  const load = useCallback(() => {
    api
      .journalEntries()
      .then((d) => setEntries((d as { entries: Entry[] }).entries))
      .catch(() => setEntries([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    setMsg("Saving…");
    try {
      const body = {
        ...form,
        pnl: Number(form.pnl) || 0,
        tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
      };
      const res = (await api.saveJournal(body)) as { status: string; message?: string };
      if (res.status === "SUCCESS") {
        setMsg("✅ Saved to Obsidian vault.");
        setForm((f) => ({ ...f, pnl: 0, tags: "", notes: "" }));
        load();
      } else {
        setMsg(`⚠️ ${res.message ?? "Save failed."}`);
      }
    } catch {
      setMsg("❌ Request failed (backend running?).");
    }
  }

  async function runAnalysis() {
    setAnalyzing(true);
    try {
      setAnalysis((await api.journalAnalysis()) as Analysis);
    } catch {
      setAnalysis(null);
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-6xl">
      <h2 className="text-2xl font-bold">Journal</h2>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* New entry */}
        <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-semibold text-amber-500">New Session Log</h3>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Date">
              <input type="date" value={form.date}
                onChange={(e) => setForm({ ...form, date: e.target.value })} className={INPUT} />
            </Field>
            <Field label="Asset">
              <select value={form.asset}
                onChange={(e) => setForm({ ...form, asset: e.target.value })} className={INPUT}>
                <option>XAUUSD+</option>
                <option>BTCUSD</option>
                <option>ETHUSD</option>
              </select>
            </Field>
            <Field label="Session">
              <select value={form.session}
                onChange={(e) => setForm({ ...form, session: e.target.value })} className={INPUT}>
                <option>Asia</option>
                <option>London</option>
                <option>New York</option>
              </select>
            </Field>
            <Field label="Net PnL ($)">
              <input type="number" step={0.01} value={form.pnl}
                onChange={(e) => setForm({ ...form, pnl: parseFloat(e.target.value) || 0 })}
                className={`${INPUT} font-mono`} />
            </Field>
          </div>
          <Field label="Tags (comma-separated)">
            <input type="text" value={form.tags} placeholder="Supply/Demand, AI Approved"
              onChange={(e) => setForm({ ...form, tags: e.target.value })} className={INPUT} />
          </Field>
          <Field label="Notes">
            <textarea rows={6} value={form.notes} placeholder="Observations, AI signal performance, playbook adjustments…"
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              className={`${INPUT} resize-none`} />
          </Field>
          <button onClick={save}
            className="w-full py-2.5 bg-amber-600 hover:bg-amber-700 rounded-lg text-sm font-bold">
            Save to Obsidian Vault
          </button>
          {msg && <p className="text-xs text-gray-300">{msg}</p>}
        </div>

        {/* Recent entries */}
        <div className="lg:col-span-2 bg-[#0a0d12] border border-gray-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-200 mb-4 flex justify-between">
            Recent Entries
            <span className="text-[10px] text-gray-500 font-normal">{entries.length} from vault</span>
          </h3>
          <div className="space-y-3 max-h-[480px] overflow-y-auto pr-1">
            {entries.length === 0 && (
              <p className="text-xs text-gray-500">
                No entries yet (or vault path not set in Settings). Saved entries appear here.
              </p>
            )}
            {entries.map((e) => (
              <div key={e.file} className="bg-[#0d1117] border border-gray-800 rounded-lg p-4">
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold px-2 py-0.5 bg-gray-800 rounded uppercase">{e.asset}</span>
                    <span className="text-[11px] text-gray-500">{e.date} · {e.session}</span>
                  </div>
                  <span className={`text-sm font-mono font-bold ${pc(e.pnl)}`}>
                    {e.pnl >= 0 ? "+" : ""}{e.pnl.toFixed(2)}
                  </span>
                </div>
                {e.notes && <p className="text-xs text-gray-400 leading-relaxed mb-2">{e.notes}</p>}
                <div className="flex gap-1.5 flex-wrap">
                  {e.tags.map((t) => (
                    <span key={t} className="text-[10px] px-2 py-0.5 bg-indigo-950/30 text-indigo-400 border border-indigo-900/50 rounded-full">
                      #{t}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Monthly analysis */}
      <div className="bg-[#0a0d12] border border-indigo-900/50 rounded-xl p-5">
        <div className="flex items-center justify-between mb-2">
          <div>
            <h3 className="text-sm font-semibold text-indigo-400">Monthly System Analysis</h3>
            <p className="text-xs text-gray-500">
              Net P/L by asset, session and tag — see where the system improves vs needs work.
            </p>
          </div>
          <button onClick={runAnalysis} disabled={analyzing}
            className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 rounded-lg text-sm font-bold">
            {analyzing ? "Analyzing…" : "Run Analysis"}
          </button>
        </div>

        {analysis && analysis.entries === 0 && (
          <p className="text-xs text-gray-500 mt-3">{analysis.message}</p>
        )}

        {analysis && analysis.entries > 0 && (
          <div className="mt-4 space-y-5">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <Stat label={`Entries (${analysis.month})`} value={String(analysis.entries)} />
              <Stat label="Total P/L" value={money(analysis.total_pnl!)} color={pc(analysis.total_pnl!)} />
              <Stat label="Avg P/L" value={money(analysis.avg_pnl!)} color={pc(analysis.avg_pnl!)} />
              <Stat label="Win Rate" value={`${analysis.win_rate_pct}%`} />
            </div>

            {analysis.insights && analysis.insights.length > 0 && (
              <ul className="text-xs text-gray-300 space-y-1 bg-[#0d1117] border border-gray-800 rounded-lg p-4">
                {analysis.insights.map((s, i) => <li key={i}>• {s}</li>)}
              </ul>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <GroupTable title="By Asset" data={analysis.by_asset!} />
              <GroupTable title="By Session" data={analysis.by_session!} />
            </div>

            {analysis.tags && analysis.tags.length > 0 && (
              <div>
                <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">Tags</p>
                <div className="flex gap-2 flex-wrap">
                  {analysis.tags.map((t) => (
                    <span key={t.tag} className="text-[11px] px-2.5 py-1 bg-[#0d1117] border border-gray-800 rounded-full">
                      #{t.tag} <span className="text-gray-500">×{t.count}</span>{" "}
                      <span className={pc(t.pnl)}>{money(t.pnl)}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function GroupTable({ title, data }: { title: string; data: Record<string, GroupStat> }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">{title}</p>
      <table className="w-full text-xs">
        <thead className="text-gray-500 border-b border-gray-800">
          <tr>
            <th className="text-left font-medium py-1.5">Key</th>
            <th className="text-right font-medium py-1.5">Trades</th>
            <th className="text-right font-medium py-1.5">Win %</th>
            <th className="text-right font-medium py-1.5">Net P/L</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(data).map(([k, g]) => (
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
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col space-y-1">
      <label className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</label>
      {children}
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
