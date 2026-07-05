"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface Settings {
  enabled: boolean;
  mode: "alert_only" | "autonomous";
  assets: string[];
  strategies: string[];
  timeframe: string;
  wiki_enabled: boolean;
}

const ALL_ASSETS = ["GOLD", "BTC", "ETH"];
const INPUT =
  "bg-[#0d1117] border border-gray-700 rounded px-2 py-1.5 text-xs outline-none focus:border-amber-600";

export function ScannerPanel() {
  const [s, setS] = useState<Settings | null>(null);
  const [strategies, setStrategies] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api
      .scannerSettings()
      .then((d) => {
        const r = d as { settings: Settings; strategies: string[] };
        setS(r.settings);
        setStrategies(r.strategies);
      })
      .catch(() => setMsg("Backend unreachable."));
  }, []);

  if (!s) return null;
  const set = (patch: Partial<Settings>) => setS({ ...s, ...patch });
  const autonomous = s.mode === "autonomous";

  function toggleAsset(a: string) {
    set({ assets: s!.assets.includes(a) ? s!.assets.filter((x) => x !== a) : [...s!.assets, a] });
  }
  function toggleStrategy(st: string) {
    set({ strategies: s!.strategies.includes(st) ? s!.strategies.filter((x) => x !== st) : [...s!.strategies, st] });
  }

  async function save() {
    setSaving(true);
    setMsg("");
    try {
      const saved = (await api.saveScannerSettings(s)) as Settings;
      setS(saved);
      setMsg(saved.enabled ? `✅ Scanner ON — ${saved.mode === "autonomous" ? "AUTONOMOUS" : "alert-only"}.` : "✅ Saved (scanner off).");
    } catch {
      setMsg("❌ Save failed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={`rounded-xl p-5 border ${autonomous && s.enabled ? "bg-rose-950/20 border-rose-900/50" : "bg-[#0a0d12] border-gray-800"}`}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-bold text-gray-200">Auto-Scanner</h3>
          <p className="text-xs text-gray-500">Watches each new closed bar and acts when a setup passes the pipeline.</p>
        </div>
        {/* Master ON/OFF */}
        <label className="flex items-center gap-2 text-xs text-gray-300">
          {s.enabled ? "ON" : "OFF"}
          <button
            onClick={() => set({ enabled: !s.enabled })}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${s.enabled ? "bg-emerald-600" : "bg-gray-700"}`}
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${s.enabled ? "translate-x-6" : "translate-x-1"}`} />
          </button>
        </label>
      </div>

      {/* Mode toggle: alert-only vs autonomous */}
      <div className="mb-4">
        <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">Mode</p>
        <div className="flex bg-[#0d1117] border border-gray-800 rounded-lg p-1 w-fit">
          <button
            onClick={() => set({ mode: "alert_only" })}
            className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-colors ${!autonomous ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-white"}`}
          >
            Alert-only
          </button>
          <button
            onClick={() => set({ mode: "autonomous" })}
            className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-colors ${autonomous ? "bg-rose-600 text-white" : "text-gray-400 hover:text-white"}`}
          >
            Autonomous
          </button>
        </div>
        <p className={`text-[11px] mt-1.5 ${autonomous ? "text-rose-400" : "text-gray-500"}`}>
          {autonomous
            ? "⚠ Places real Demo orders automatically when a setup passes."
            : "Sends a Telegram “setup found” alert only — you place the trade."}
        </p>
      </div>

      {/* Deployed config */}
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wider text-gray-500">Strategies (run together)</span>
          <div className="flex gap-2 flex-wrap max-w-md">
            {strategies.map((st) => (
              <button
                key={st}
                onClick={() => toggleStrategy(st)}
                className={`px-2.5 py-1.5 text-[11px] rounded-md border transition-colors ${s.strategies.includes(st) ? "bg-amber-600/20 border-amber-600 text-amber-300" : "border-gray-700 text-gray-500"}`}
              >
                {st}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wider text-gray-500">Timeframe</span>
          <select value={s.timeframe} onChange={(e) => set({ timeframe: e.target.value })} className={INPUT}>
            {["M15", "M30", "H1", "H4", "D1"].map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wider text-gray-500">Assets</span>
          <div className="flex gap-2">
            {ALL_ASSETS.map((a) => (
              <button
                key={a}
                onClick={() => toggleAsset(a)}
                className={`px-3 py-1.5 text-xs rounded-md border transition-colors ${s.assets.includes(a) ? "bg-amber-600/20 border-amber-600 text-amber-300" : "border-gray-700 text-gray-500"}`}
              >
                {a}
              </button>
            ))}
          </div>
        </div>
        <label className="flex items-center gap-2 text-xs text-gray-400">
          <input type="checkbox" checked={s.wiki_enabled} onChange={(e) => set({ wiki_enabled: e.target.checked })} />
          Wiki screen
        </label>
        <button
          onClick={save}
          disabled={saving}
          className="ml-auto px-5 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 rounded-lg text-sm font-bold"
        >
          {saving ? "Saving…" : "Save Scanner"}
        </button>
      </div>
      {msg && <p className="text-xs text-gray-300 mt-3">{msg}</p>}
    </div>
  );
}
