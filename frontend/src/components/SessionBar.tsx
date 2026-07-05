"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface SessionDef {
  key: string;
  name: string;
  startMin: number;
  endMin: number; // > 1440 means it wraps past midnight (e.g. New York)
  band: string;
  dot: string;
  text: string;
}

// Trading sessions in IST (minutes from midnight). These reproduce the standard
// Asia/London/New York windows for Asia/Kolkata.
const SESSIONS: SessionDef[] = [
  { key: "AS", name: "Asia", startMin: 5 * 60 + 30, endMin: 14 * 60 + 30, band: "bg-amber-500/40", dot: "bg-amber-500", text: "text-amber-400" },
  { key: "LN", name: "London", startMin: 12 * 60 + 30, endMin: 21 * 60 + 30, band: "bg-blue-500/40", dot: "bg-blue-500", text: "text-blue-400" },
  { key: "NY", name: "New York", startMin: 18 * 60 + 30, endMin: 26 * 60 + 30, band: "bg-rose-500/40", dot: "bg-rose-500", text: "text-rose-400" },
];

interface EconEvent {
  title: string;
  country: string;
  impact: string;
  iso: string;
}

// Format the feed's ISO datetime to "Wed 18:00" in IST.
function fmtEvent(iso: string): string {
  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Kolkata", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(new Date(iso));
  } catch {
    return "";
  }
}

function istNowMinutes(): number {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(new Date());
  const h = Number(parts.find((p) => p.type === "hour")?.value ?? 0);
  const m = Number(parts.find((p) => p.type === "minute")?.value ?? 0);
  return h * 60 + m;
}

const pct = (min: number) => (min / 1440) * 100;
const clock = (min: number) =>
  `${String(Math.floor(min / 60) % 24).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;
const dur = (min: number) => {
  const h = Math.floor(min / 60);
  return h > 0 ? `${h}h ${min % 60}m` : `${min % 60}m`;
};
const isActive = (s: SessionDef, now: number) =>
  s.endMin <= 1440 ? now >= s.startMin && now < s.endMin : now >= s.startMin || now < s.endMin - 1440;

interface Seg { left: number; width: number; band: string; text: string; key: string; label: boolean }
function segments(s: SessionDef): Seg[] {
  if (s.endMin <= 1440) {
    return [{ left: pct(s.startMin), width: pct(s.endMin - s.startMin), band: s.band, text: s.text, key: s.key, label: true }];
  }
  const w1 = 1440 - s.startMin;
  const w2 = s.endMin - 1440;
  return [
    { left: pct(s.startMin), width: pct(w1), band: s.band, text: s.text, key: s.key, label: w1 >= w2 },
    { left: 0, width: pct(w2), band: s.band, text: s.text, key: s.key, label: w2 > w1 },
  ];
}

export function SessionBar() {
  const [now, setNow] = useState<number | null>(null);
  const [events, setEvents] = useState<EconEvent[]>([]);

  useEffect(() => {
    const tick = () => setNow(istNowMinutes());
    tick();
    const t = setInterval(tick, 20000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const load = () =>
      api
        .events()
        .then((d) => setEvents((d as { events: EconEvent[] }).events ?? []))
        .catch(() => setEvents([]));
    load();
    const t = setInterval(load, 30 * 60 * 1000); // refresh every 30 min
    return () => clearInterval(t);
  }, []);

  if (now === null) return null;

  const active = SESSIONS.filter((s) => isActive(s, now));
  const current = active.length ? active[active.length - 1] : null;

  let next: SessionDef | null = null;
  let nextIn = Infinity;
  for (const s of SESSIONS) {
    if (isActive(s, now)) continue;
    const diff = (s.startMin - now + 1440) % 1440;
    if (diff < nextIn) {
      nextIn = diff;
      next = s;
    }
  }
  const closesIn = current ? ((current.endMin % 1440) - now + 1440) % 1440 : 0;

  return (
    <div className="bg-[#0a0d12] border border-gray-800 rounded-xl overflow-hidden">
      {/* Events ticker (high-impact USD — moves Gold/BTC/ETH) */}
      <div className="flex items-center gap-3 text-xs px-4 py-2 border-b border-gray-800 bg-[#0d1117]">
        <span className="shrink-0">📅</span>
        {events.length === 0 ? (
          <span className="text-gray-400">No high-impact events this week</span>
        ) : (
          <div className="flex gap-5 overflow-x-auto no-scrollbar">
            {events.map((e, i) => {
              const past = new Date(e.iso).getTime() < Date.now();
              return (
                <span
                  key={i}
                  className={`whitespace-nowrap flex items-center gap-1.5 ${past ? "opacity-40" : ""}`}
                  title={past ? "Already released" : "Upcoming"}
                >
                  <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${past ? "bg-gray-500" : "bg-rose-500 animate-pulse"}`} />
                  <span className="text-gray-500 font-mono">{fmtEvent(e.iso)}</span>
                  <span className={past ? "text-gray-400" : "text-gray-200"}>{e.country} {e.title}</span>
                </span>
              );
            })}
          </div>
        )}
      </div>

      {/* Session pills */}
      <div className="flex items-center justify-between gap-3 px-4 py-2.5 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          {current ? (
            <span className="flex items-center gap-2 bg-[#0d1117] border border-gray-800 rounded-md px-3 py-1.5 text-xs">
              <span className={`h-2 w-2 rounded-full ${current.dot}`} />
              <span className={`font-semibold ${current.text}`}>{current.name}</span>
              <span className="text-gray-500 font-mono">
                {clock(current.startMin)} – {clock(current.endMin)} IST
              </span>
            </span>
          ) : (
            <span className="text-xs text-gray-500">Between sessions</span>
          )}
          {next && (
            <span className="flex items-center gap-2 bg-[#0d1117] border border-gray-800 rounded-md px-3 py-1.5 text-xs">
              <span className="text-gray-500 uppercase tracking-wider text-[10px]">Next</span>
              <span className={`h-2 w-2 rounded-full ${next.dot}`} />
              <span className={`font-semibold ${next.text}`}>{next.name}</span>
              <span className="text-gray-300 font-mono">{dur(nextIn)}</span>
            </span>
          )}
        </div>
        {current && (
          <span className="text-xs bg-amber-950/30 border border-amber-900/50 text-amber-300 rounded-md px-3 py-1.5">
            {current.name} closes in{" "}
            <span className="font-mono font-semibold">{dur(closesIn)}</span>
          </span>
        )}
      </div>

      {/* 24H session map */}
      <div className="px-4 pb-3">
        <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">24H Session Map (IST)</p>
        <div className="relative h-6 bg-[#0d1117] rounded border border-gray-800 overflow-hidden">
          {SESSIONS.flatMap(segments).map((seg, i) => (
            <div
              key={i}
              className={`absolute top-0 bottom-0 ${seg.band} flex items-center justify-center`}
              style={{ left: `${seg.left}%`, width: `${seg.width}%` }}
            >
              {seg.label && <span className={`text-[10px] font-bold ${seg.text}`}>{seg.key}</span>}
            </div>
          ))}
          {/* now marker */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-white shadow-[0_0_6px_rgba(255,255,255,0.7)]"
            style={{ left: `${pct(now)}%` }}
          />
        </div>
        <div className="flex justify-between text-[9px] text-gray-600 mt-1 font-mono">
          {["00", "03", "06", "09", "12", "15", "18", "21", "24"].map((h) => (
            <span key={h}>{h}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
