"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function SettingsPage() {
  const [tg, setTg] = useState<{ enabled: boolean; configured: boolean } | null>(null);
  const [msg, setMsg] = useState<string>("");

  useEffect(() => {
    api.telegramStatus().then(setTg as any).catch(() => setTg(null));
  }, []);

  async function test(kind: "entry" | "exit") {
    setMsg("Sending…");
    try {
      const res =
        kind === "entry"
          ? await api.telegramTestEntry()
          : await api.telegramTestExit();
      setMsg((res as any).sent ? "✅ Sent — check Telegram." : "⚠️ Not sent (see backend log / token).");
    } catch {
      setMsg("❌ Request failed (backend running?).");
    }
  }

  return (
    <div className="p-8 max-w-3xl space-y-6">
      <h2 className="text-2xl font-bold">Settings</h2>

      <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-6 space-y-4">
        <h3 className="text-lg font-semibold text-amber-500">Telegram Alerts</h3>
        <p className="text-sm text-gray-400">
          Configure <code>TELEGRAM_BOT_TOKEN</code> and <code>TELEGRAM_CHAT_ID</code> in
          the root <code>.env</code>, then send test alerts.
        </p>
        <div className="text-xs text-gray-400">
          Status:{" "}
          <span className={tg?.configured ? "text-emerald-400" : "text-rose-400"}>
            {tg ? (tg.configured ? "configured" : "not configured") : "unknown"}
          </span>{" "}
          · enabled: {tg?.enabled ? "yes" : "no"}
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => test("entry")}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm font-semibold"
          >
            Test Entry Alert
          </button>
          <button
            onClick={() => test("exit")}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg text-sm font-semibold"
          >
            Test Exit Alert
          </button>
        </div>
        {msg && <p className="text-sm text-gray-300">{msg}</p>}
      </div>

      <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-6 space-y-2">
        <h3 className="text-lg font-semibold text-amber-500">MT5 & Obsidian</h3>
        <p className="text-sm text-gray-400">
          Credentials and paths live in the root <code>.env</code> for safety. The live
          kill-switch <code>ALLOW_LIVE</code> must be <code>true</code> before any
          real-money order is accepted.
        </p>
      </div>
    </div>
  );
}
