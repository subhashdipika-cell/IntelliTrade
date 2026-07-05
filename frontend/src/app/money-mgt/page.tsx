"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

interface Account {
  balance: number;
  equity: number;
  margin_free: number;
  currency: string;
}
interface Settings {
  base_lots: number;
  lots_by_asset: Record<string, number>;
  risk_per_trade_pct: number;
  max_daily_loss_pct: number;
  rr_ratio: string;
  max_open_trades: number;
  hard_stop_override: boolean;
  // trailing stop
  trailing_enabled: boolean;
  be_trigger_pct: number;
  be_buffer_r: number;
  trail_trigger_pct: number;
  trail_r_mult: number;
  near_target_pct: number;
  near_target_r_mult: number;
  // daily profit lock
  profit_lock_enabled: boolean;
  profit_lock_pct: number;
  profit_giveback_pct: number;
  // structure-aware target
  target_cap_enabled: boolean;
  resistance_lookback: number;
  min_rr_after_cap: number;
  skip_low_rr: boolean;
}
interface Overview {
  connected: boolean;
  account: Account | null;
  drawdown_pct: number | null;
  open_trades: number;
  active_account: "DEMO" | "LIVE";
  allow_live: boolean;
  has_live: boolean;
  settings: Settings;
  daily?: { pnl: number; peak: number; trades: number; balance: number | null };
  profit_lock?: { active: boolean; reason: string; target: number | null };
}

const INPUT =
  "bg-[#0d1117] border border-gray-700 rounded px-2 py-2 text-sm w-full outline-none focus:border-amber-600 font-mono";
const money = (v: number | undefined, ccy = "USD") =>
  v === undefined ? "—" : `${ccy} ${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function MoneyMgmtPage() {
  const [ov, setOv] = useState<Overview | null>(null);
  const [form, setForm] = useState<Settings | null>(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(() => {
    api
      .moneyOverview()
      .then((d) => {
        const o = d as Overview;
        setOv(o);
        setForm(o.settings);
      })
      .catch(() => setMsg("Backend unreachable — start it on :8100."));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const set = (k: keyof Settings, v: number | string | boolean | Record<string, number>) =>
    setForm((f) => (f ? { ...f, [k]: v } : f));

  const setLot = (asset: string, v: number) =>
    setForm((f) => (f ? { ...f, lots_by_asset: { ...f.lots_by_asset, [asset]: v } } : f));

  const ASSETS = ["BTC", "ETH", "GOLD"];

  async function save() {
    if (!form) return;
    setSaving(true);
    setMsg("");
    try {
      const saved = (await api.saveMoneySettings(form)) as Settings;
      setForm(saved);
      setMsg("✅ Saved — these now drive the Risk stage on every signal.");
      load();
    } catch {
      setMsg("❌ Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function switchAccount(target: "DEMO" | "LIVE") {
    if (target === "LIVE") {
      if (!confirm("Switch to the REAL-MONEY (LIVE) account? Orders will execute with real funds.")) return;
    }
    setMsg("Switching account…");
    try {
      const res = (await api.switchAccount(target)) as { ok: boolean; reason?: string };
      setMsg(res.ok ? `✅ Now on ${target} account.` : `⚠️ ${res.reason ?? "Switch refused."}`);
      load();
    } catch {
      setMsg("❌ Switch request failed.");
    }
  }

  const acct = ov?.account ?? undefined;
  const ccy = acct?.currency ?? "USD";
  const isLive = ov?.active_account === "LIVE";

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <h2 className="text-2xl font-bold">Money Management</h2>

      {/* Trading account: DEMO / LIVE */}
      {ov && (
        <div
          className={`rounded-xl p-5 border ${
            isLive ? "bg-rose-950/25 border-rose-900/60" : "bg-[#0a0d12] border-gray-800"
          }`}
        >
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-gray-500">Trading Account</p>
              <p className={`text-lg font-bold ${isLive ? "text-rose-400" : "text-emerald-400"}`}>
                {isLive ? "🔴 LIVE — Real Money" : "🟢 DEMO"}
                {ov.account && (
                  <span className="text-xs font-normal text-gray-500 ml-2">{ov.account.currency}</span>
                )}
              </p>
            </div>
            <div className="flex bg-[#0d1117] border border-gray-800 rounded-lg p-1">
              <button
                onClick={() => switchAccount("DEMO")}
                className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                  !isLive ? "bg-emerald-600 text-white" : "text-gray-400 hover:text-white"
                }`}
              >
                Demo
              </button>
              <button
                onClick={() => switchAccount("LIVE")}
                disabled={!ov.allow_live || !ov.has_live}
                title={
                  !ov.allow_live
                    ? "Set ALLOW_LIVE=true in .env to enable"
                    : !ov.has_live
                      ? "Add MT5_LIVE_* credentials in .env"
                      : "Switch to real-money account"
                }
                className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                  isLive ? "bg-rose-600 text-white" : "text-gray-400 hover:text-white"
                } disabled:opacity-40 disabled:cursor-not-allowed`}
              >
                Live
              </button>
            </div>
          </div>
          <p className="text-[11px] text-gray-500 mt-2">
            {!ov.allow_live
              ? "Live is locked — set ALLOW_LIVE=true in .env (and add MT5_LIVE_* credentials), then restart."
              : !ov.has_live
                ? "Add MT5_LIVE_LOGIN/PASSWORD/SERVER in .env, then restart, to enable Live."
                : isLive
                  ? "⚠ Real-money mode. Every approved signal executes with real funds."
                  : "Live is available — it runs on its own separate MT5 terminal (isolated from demo)."}
          </p>
        </div>
      )}

      {/* Live MT5 figures */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card title="Balance" value={money(acct?.balance, ccy)} />
        <Card title="Equity" value={money(acct?.equity, ccy)} />
        <Card
          title="Drawdown"
          value={ov?.drawdown_pct === null || ov?.drawdown_pct === undefined ? "—" : `${ov.drawdown_pct}%`}
          color={(ov?.drawdown_pct ?? 0) < 0 ? "text-rose-400" : "text-emerald-400"}
        />
        <Card title="Free Margin" value={money(acct?.margin_free, ccy)} />
      </div>

      {!ov?.connected && (
        <div className="bg-amber-950/30 border border-amber-900/50 text-amber-300 text-sm rounded-lg p-4">
          MT5 not connected (stub mode). Figures show once the terminal is running on your laptop.
          Guardrail settings below still save and drive the Risk stage.
        </div>
      )}

      {/* Guardrails — persisted, source of truth for Risk stage */}
      {form && (
        <div className="bg-[#0a0d12] border border-gray-800 rounded-xl p-6 space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-amber-500">Execution Guardrails</h3>
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">
              Open trades: {ov?.open_trades ?? 0} / {form.max_open_trades}
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-3 gap-5">
            {ASSETS.map((a) => (
              <Field key={a} label={`Lot Size — ${a}`}>
                <input type="number" step={0.01}
                  value={form.lots_by_asset?.[a] ?? form.base_lots}
                  onChange={(e) => setLot(a, parseFloat(e.target.value) || 0)} className={INPUT} />
              </Field>
            ))}
            <Field label="Risk per Trade %">
              <input type="number" step={0.1} value={form.risk_per_trade_pct}
                onChange={(e) => set("risk_per_trade_pct", parseFloat(e.target.value) || 0)} className={INPUT} />
            </Field>
            <Field label="Max Daily Loss %">
              <input type="number" step={0.5} value={form.max_daily_loss_pct}
                onChange={(e) => set("max_daily_loss_pct", parseFloat(e.target.value) || 0)} className={INPUT} />
            </Field>
            <Field label="Target R:R">
              <input type="text" value={form.rr_ratio}
                onChange={(e) => set("rr_ratio", e.target.value)} className={INPUT} />
            </Field>
            <Field label="Max Open Trades">
              <input type="number" step={1} value={form.max_open_trades}
                onChange={(e) => set("max_open_trades", parseInt(e.target.value) || 0)} className={INPUT} />
            </Field>
          </div>

          {/* Hard-stop override */}
          <div
            className={`flex items-center justify-between border rounded-lg p-4 ${
              form.hard_stop_override ? "bg-rose-950/30 border-rose-900/50" : "bg-[#0d1117] border-gray-800"
            }`}
          >
            <div>
              <p className="text-sm font-semibold text-white">Manual Limit Override</p>
              <p className={`text-xs mt-1 ${form.hard_stop_override ? "text-rose-400" : "text-gray-500"}`}>
                {form.hard_stop_override
                  ? "⚠ Daily-loss hard stop is IGNORED. System keeps executing."
                  : "Safe mode: execution halts when Max Daily Loss is reached."}
              </p>
            </div>
            <button
              onClick={() => set("hard_stop_override", !form.hard_stop_override)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                form.hard_stop_override ? "bg-rose-600" : "bg-gray-700"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  form.hard_stop_override ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
          </div>

          {/* Daily profit lock — bank the day, stop fresh entries */}
          <div className="border-t border-gray-800 pt-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-amber-500">Daily Profit Lock</h3>
                <p className="text-[11px] text-gray-500 mt-0.5">
                  Once today&apos;s realised P&amp;L reaches the target, no NEW positions open for the
                  rest of the day — open trades keep trailing. The give-back stop locks earlier if a
                  green day starts bleeding back (arms once the day peaks at ≥ half the target).
                  Not affected by the Manual Limit Override.
                </p>
              </div>
              <Toggle on={form.profit_lock_enabled} onClick={() => set("profit_lock_enabled", !form.profit_lock_enabled)} />
            </div>
            {form.profit_lock_enabled && (
              <>
                {ov?.profit_lock?.active && (
                  <div className="bg-emerald-950/30 border border-emerald-900/50 text-emerald-300 text-sm rounded-lg p-3">
                    🔒 LOCKED for today — {ov.profit_lock.reason}. New entries resume tomorrow.
                  </div>
                )}
                <div className="grid grid-cols-2 md:grid-cols-3 gap-5">
                  <Field label="Lock at profit (% of balance)">
                    <input type="number" step={0.25} value={form.profit_lock_pct}
                      onChange={(e) => set("profit_lock_pct", parseFloat(e.target.value) || 0)} className={INPUT} />
                  </Field>
                  <Field label="Give-back stop (% off peak)">
                    <input type="number" step={5} value={form.profit_giveback_pct}
                      onChange={(e) => set("profit_giveback_pct", parseFloat(e.target.value) || 0)} className={INPUT} />
                  </Field>
                  <div className="flex flex-col space-y-1">
                    <label className="text-[10px] text-gray-500 uppercase tracking-wider">Today (realised)</label>
                    <div className="flex items-center h-[38px] font-mono text-sm">
                      <span className={(ov?.daily?.pnl ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}>
                        {ov?.daily ? `${ov.daily.pnl >= 0 ? "+" : ""}${ov.daily.pnl.toFixed(2)}` : "—"}
                      </span>
                      <span className="text-[11px] text-gray-500 ml-3">
                        peak {ov?.daily ? `+${ov.daily.peak.toFixed(2)}` : "—"}
                        {ov?.profit_lock?.target != null && ` · target +${ov.profit_lock.target.toFixed(2)}`}
                      </span>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Trailing stop — profit protection */}
          <div className="border-t border-gray-800 pt-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-amber-500">Trailing Stop</h3>
                <p className="text-[11px] text-gray-500 mt-0.5">
                  Ratchets the stop toward profit as price approaches target — turns a near-miss
                  into breakeven instead of a full stop-out. Triggers are % of the way to target;
                  give-backs are in units of initial risk (R).
                </p>
              </div>
              <Toggle on={form.trailing_enabled} onClick={() => set("trailing_enabled", !form.trailing_enabled)} />
            </div>
            {form.trailing_enabled && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-5">
                <Field label="Breakeven trigger %">
                  <input type="number" step={5} value={form.be_trigger_pct}
                    onChange={(e) => set("be_trigger_pct", parseFloat(e.target.value) || 0)} className={INPUT} />
                </Field>
                <Field label="Breakeven buffer (×R)">
                  <input type="number" step={0.05} value={form.be_buffer_r}
                    onChange={(e) => set("be_buffer_r", parseFloat(e.target.value) || 0)} className={INPUT} />
                </Field>
                <Field label="Trail trigger %">
                  <input type="number" step={5} value={form.trail_trigger_pct}
                    onChange={(e) => set("trail_trigger_pct", parseFloat(e.target.value) || 0)} className={INPUT} />
                </Field>
                <Field label="Trail give-back (×R)">
                  <input type="number" step={0.1} value={form.trail_r_mult}
                    onChange={(e) => set("trail_r_mult", parseFloat(e.target.value) || 0)} className={INPUT} />
                </Field>
                <Field label="Near-target trigger %">
                  <input type="number" step={5} value={form.near_target_pct}
                    onChange={(e) => set("near_target_pct", parseFloat(e.target.value) || 0)} className={INPUT} />
                </Field>
                <Field label="Near-target give-back (×R)">
                  <input type="number" step={0.1} value={form.near_target_r_mult}
                    onChange={(e) => set("near_target_r_mult", parseFloat(e.target.value) || 0)} className={INPUT} />
                </Field>
              </div>
            )}
          </div>

          {/* Structure-aware target */}
          <div className="border-t border-gray-800 pt-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-amber-500">Smart Targets</h3>
                <p className="text-[11px] text-gray-500 mt-0.5">
                  Caps each signal&apos;s target just below the nearest swing resistance (longs) /
                  support (shorts), so it never aims past a wall price is unlikely to break.
                </p>
              </div>
              <Toggle on={form.target_cap_enabled} onClick={() => set("target_cap_enabled", !form.target_cap_enabled)} />
            </div>
            {form.target_cap_enabled && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-5">
                <Field label="Resistance lookback (bars)">
                  <input type="number" step={1} value={form.resistance_lookback}
                    onChange={(e) => set("resistance_lookback", parseInt(e.target.value) || 0)} className={INPUT} />
                </Field>
                <Field label="Min R:R after cap">
                  <input type="number" step={0.1} value={form.min_rr_after_cap}
                    onChange={(e) => set("min_rr_after_cap", parseFloat(e.target.value) || 0)} className={INPUT} />
                </Field>
                <div className="flex flex-col space-y-1">
                  <label className="text-[10px] text-gray-500 uppercase tracking-wider">Skip if RR too low</label>
                  <div className="flex items-center h-[38px]">
                    <Toggle on={form.skip_low_rr} onClick={() => set("skip_low_rr", !form.skip_low_rr)} />
                    <span className="text-[11px] text-gray-500 ml-3">
                      {form.skip_low_rr ? "Blocks the trade" : "Caps target only"}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={save}
              disabled={saving}
              className="px-6 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 rounded-lg text-sm font-bold"
            >
              {saving ? "Saving…" : "Save Settings"}
            </button>
            {msg && <span className="text-sm text-gray-300">{msg}</span>}
          </div>
        </div>
      )}
    </div>
  );
}

function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
        on ? "bg-emerald-600" : "bg-gray-700"
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
          on ? "translate-x-6" : "translate-x-1"
        }`}
      />
    </button>
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col space-y-1">
      <label className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</label>
      {children}
    </div>
  );
}
