"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { SessionBar } from "@/components/SessionBar";

const TV = {
  BTC: "BINANCE:BTCUSDT",
  ETH: "BINANCE:ETHUSDT",
  GOLD: "OANDA:XAUUSD",
} as const;

export default function Dashboard() {
  const [health, setHealth] = useState<string>("checking…");
  const [now, setNow] = useState<string>("");

  useEffect(() => {
    api
      .health()
      .then(() => setHealth("ONLINE"))
      .catch(() => setHealth("OFFLINE (start backend on :8100)"));
  }, []);

  useEffect(() => {
    const tick = () =>
      setNow(new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" }));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);

  const online = health === "ONLINE";

  return (
    <div className="p-6 space-y-6">
      {/* Banner — click to refresh the dashboard */}
      <button
        onClick={() => window.location.reload()}
        title="Click to refresh"
        aria-label="Refresh dashboard"
        className="block w-full rounded-xl overflow-hidden border border-gray-800 cursor-pointer transition-all hover:border-gray-600 hover:brightness-110 active:scale-[0.995] focus:outline-none focus:ring-1 focus:ring-emerald-700"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/intellitrade-banner.png"
          alt="IntelliTrade — the most methodical and disciplined trade engineer"
          className="w-full h-auto select-none"
          draggable={false}
        />
      </button>

      {/* Header: logo (refresh) left, status right */}
      <header className="flex items-center justify-between gap-4 bg-gradient-to-r from-[#0a0d12] to-[#0d1117] border border-gray-800 rounded-xl px-5 py-3">
        <div>
          <h2 className="text-lg font-bold">Command Center</h2>
          <p className="text-xs text-gray-500">Live market overview</p>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-2 bg-[#0d1117] border border-gray-800 rounded-full px-3 py-1.5">
            <span className="text-[11px] text-gray-500 uppercase tracking-wider">IST</span>
            <span className="text-xs font-mono text-gray-300 tabular-nums">{now || "—"}</span>
          </div>
          <div
            className={`flex items-center gap-2 rounded-full px-3 py-1.5 border ${
              online
                ? "bg-emerald-950/30 border-emerald-900/50"
                : "bg-rose-950/30 border-rose-900/50"
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${online ? "bg-emerald-500 animate-pulse" : "bg-rose-500"}`}
            />
            <span className={`text-xs font-medium ${online ? "text-emerald-400" : "text-rose-400"}`}>
              {online ? "Backend Online" : health}
            </span>
          </div>
        </div>
      </header>

      <SessionBar />

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {(Object.keys(TV) as (keyof typeof TV)[]).map((asset) => (
          <div
            key={asset}
            className="bg-[#0a0d12] border border-gray-800 rounded-xl overflow-hidden"
          >
            <div className="px-4 py-2 border-b border-gray-800 text-xs font-bold uppercase tracking-wide text-gray-300">
              {asset}
            </div>
            <iframe
              title={asset}
              className="w-full h-[320px]"
              src={`https://s.tradingview.com/widgetembed/?symbol=${encodeURIComponent(
                TV[asset]
              )}&interval=60&theme=dark&style=1&hide_side_toolbar=1`}
            />
          </div>
        ))}
      </section>

      <section className="bg-[#0a0d12] border border-gray-800 rounded-xl p-4">
        <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400 mb-2">
          Pipeline
        </h3>
        <p className="text-xs text-gray-500 font-mono">
          Market → Analysis → Strategy → AI Filter → Wiki Filter → Risk → Execution → Monitoring → Learning
        </p>
      </section>
    </div>
  );
}
