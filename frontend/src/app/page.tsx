"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { SessionBar } from "@/components/SessionBar";

interface RuntimeHealth {
  status: "ok" | "degraded";
  mt5?: { connected?: boolean; verified_type?: string | null };
}

interface ScannerRuntime {
  enabled: boolean;
  mode: "alert_only" | "autonomous";
  scan_interval_seconds: number;
  scan_count: number;
  last_scan_completed_at: string | null;
}

interface ScannerConfig {
  assets: string[];
  strategies: string[];
  strategies_by_asset?: Record<string, string[]>;
  timeframe: string;
}

interface MonitoredRuntime {
  count: number;
}

const TV = {
  BTC: "BINANCE:BTCUSDT",
  ETH: "BINANCE:ETHUSDT",
  GOLD: "OANDA:XAUUSD",
} as const;

export default function Dashboard() {
  const [health, setHealth] = useState<RuntimeHealth | null>(null);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [scanner, setScanner] = useState<ScannerRuntime | null>(null);
  const [scannerConfig, setScannerConfig] = useState<ScannerConfig | null>(null);
  const [monitored, setMonitored] = useState<MonitoredRuntime | null>(null);
  const [now, setNow] = useState<string>("");

  // Poll after startup and keep the broker, scanner, and tracked-position
  // indicators current while the dashboard stays open.
  useEffect(() => {
    let alive = true;
    const check = async () => {
      try {
        const result = (await api.health()) as RuntimeHealth;
        if (alive) {
          setHealth(result);
          setApiOnline(true);
        }
      } catch {
        if (alive) {
          setApiOnline(false);
          setHealth(null);
        }
      }
      const [scannerResult, configResult, monitoredResult] = await Promise.allSettled([
        api.scannerStatus(),
        api.scannerSettings(),
        api.monitored(),
      ]);
      if (!alive) return;
      if (scannerResult.status === "fulfilled") setScanner(scannerResult.value as ScannerRuntime);
      if (configResult.status === "fulfilled") {
        setScannerConfig((configResult.value as { settings: ScannerConfig }).settings);
      }
      if (monitoredResult.status === "fulfilled") setMonitored(monitoredResult.value as MonitoredRuntime);
    };
    check();
    const t = setInterval(check, 10000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  useEffect(() => {
    const tick = () =>
      setNow(new Date().toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" }));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);

  const online = apiOnline === true;
  const mt5Connected = health?.mt5?.connected === true;
  const verifiedType = health?.mt5?.verified_type;
  const scanAgeMs = scanner?.last_scan_completed_at
    ? Date.now() - new Date(scanner.last_scan_completed_at).getTime()
    : null;
  const scanIsFresh = scanAgeMs !== null && scanAgeMs <= Math.max(180, (scanner?.scan_interval_seconds ?? 60) * 3) * 1000;
  const deployedStrategies = scannerConfig
    ? scannerConfig.assets.flatMap((asset) => {
        const selected = scannerConfig.strategies_by_asset?.[asset] ?? scannerConfig.strategies;
        return selected.map((strategy) => `${asset}: ${strategy}`);
      })
    : [];

  const formatTime = (value: string | null | undefined) =>
    value
      ? new Date(value).toLocaleString("en-IN", {
          timeZone: "Asia/Kolkata",
          dateStyle: "medium",
          timeStyle: "short",
        })
      : "No completed scan yet";

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
          src="/intellitrade-banner.webp"
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
              className={`h-2 w-2 rounded-full ${apiOnline === null ? "bg-amber-500" : online ? "bg-emerald-500 animate-pulse" : "bg-rose-500"}`}
            />
            <span className={`text-xs font-medium ${apiOnline === null ? "text-amber-400" : online ? "text-emerald-400" : "text-rose-400"}`}>
              {apiOnline === null ? "Checking backend…" : online ? "Backend online" : "Backend offline — start :8100"}
            </span>
          </div>
        </div>
      </header>

      <section aria-label="Runtime readiness" className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
        <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-4">
          <p className="text-[10px] uppercase tracking-wider text-gray-500">MT5 connection</p>
          <p className={`mt-2 text-sm font-semibold ${mt5Connected ? verifiedType === "DEMO" ? "text-emerald-400" : "text-amber-400" : "text-rose-400"}`}>
            {!online ? "Backend unavailable" : !mt5Connected ? "Disconnected" : `${verifiedType ?? "Connected"} account`}
          </p>
          <p className="mt-1 text-[11px] text-gray-500">
            {mt5Connected && verifiedType === "DEMO" ? "Broker connection verified as DEMO." : mt5Connected ? "Check the account type before enabling autonomous trading." : "Backend liveness does not mean the broker is ready."}
          </p>
        </div>

        <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-4">
          <p className="text-[10px] uppercase tracking-wider text-gray-500">Auto-scanner</p>
          <p className={`mt-2 text-sm font-semibold ${scanner?.enabled ? scanner.mode === "autonomous" ? "text-rose-400" : "text-indigo-300" : "text-gray-400"}`}>
            {!scanner ? "Checking…" : !scanner.enabled ? "Disabled" : scanner.mode === "autonomous" ? "Autonomous — automatic orders" : "Alert-only"}
          </p>
          <p className="mt-1 text-[11px] text-gray-500">
            {scanner ? `${scanner.scan_count} scan cycles · ${scanner.enabled ? scanIsFresh ? "recent scan" : "scan stale or waiting" : "not scanning while disabled"}` : "Scanner status unavailable."}
          </p>
        </div>

        <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-4">
          <p className="text-[10px] uppercase tracking-wider text-gray-500">Last scan completed</p>
          <p className={`mt-2 text-sm font-semibold ${scanner?.enabled && !scanIsFresh ? "text-amber-400" : "text-gray-200"}`}>
            {formatTime(scanner?.last_scan_completed_at)}
          </p>
          {scanner?.enabled && !scanIsFresh && <p className="mt-1 text-[11px] text-amber-400">No completed scan in the last 3 minutes.</p>}
        </div>

        <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-4">
          <p className="text-[10px] uppercase tracking-wider text-gray-500">Monitored positions</p>
          <p className="mt-2 text-sm font-semibold text-gray-200">{monitored ? monitored.count : "—"}</p>
          <p className="mt-1 text-[11px] text-gray-500">Positions currently tracked for close monitoring.</p>
        </div>
      </section>

      <section className="bg-[#0a0d12] border border-gray-800 rounded-xl p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400">Scanner deployment</h3>
          {scannerConfig && <span className="text-[11px] text-gray-500">Configured timeframe: {scannerConfig.timeframe}</span>}
        </div>
        {deployedStrategies.length ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {deployedStrategies.map((item) => <span key={item} className="rounded-md border border-gray-800 bg-[#0d1117] px-2.5 py-1.5 text-xs text-gray-300">{item}</span>)}
          </div>
        ) : (
          <p className="mt-2 text-xs text-gray-500">No strategies are assigned to the configured assets.</p>
        )}
      </section>

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
