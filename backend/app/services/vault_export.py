"""Auto-export to the Obsidian vault for later analysis / fine-tuning.

Writes two kinds of Obsidian-friendly records (YAML frontmatter for the RAG +
human reading, PLUS a fenced ```json data block for machine analysis), each
tagged with the market regime so you can later answer "which strategy works in
which regime":

  • closed trades   → obsidian_trades_dir    (demo + live, on close)
  • weekly backtest → obsidian_backtests_dir (all strategies × assets snapshot)

Everything here is fail-soft: a vault write must never break trade monitoring or
the scheduler. Gated by `obsidian_autolog_enabled`.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from app.core.config import settings
from app.core.logging_setup import get_logger
from app.services import regime

log = get_logger("services.vault_export")


def _write(path: str, text: str) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return True
    except Exception as exc:  # noqa: BLE001 — never raise into callers
        log.warning("Vault write failed (%s): %s", path, exc)
        return False


def _regime_for(asset: str, timeframe: str, df) -> dict:
    """Regime from the trade's own bars if given, else a fresh pull."""
    try:
        if df is not None and len(df) >= 60:
            return regime.classify(df)
        from app.services import market_data
        fresh = market_data.get_ohlcv(asset, timeframe or "H1", 2000, "mt5")
        return regime.classify(fresh)
    except Exception as exc:  # noqa: BLE001
        log.warning("Regime classify failed for %s: %s", asset, exc)
        return {"label": "Unknown"}


# ── Closed-trade export ───────────────────────────────────────────────────────
def export_trade(record: dict, df=None, account: str | None = None) -> bool:
    """Write one closed-trade note. `record` is a history_store record."""
    if not settings.obsidian_autolog_enabled or not settings.obsidian_trades_dir:
        return False
    asset = record.get("asset", "?")
    tf = record.get("timeframe") or "H1"
    reg = _regime_for(asset, tf, df)
    acct = (account or "DEMO").upper()
    pnl = record.get("pnl")
    outcome = record.get("outcome", "?")
    closed = (record.get("closed_at") or datetime.now(timezone.utc).isoformat())
    strat = record.get("strategy") or "—"
    ticket = record.get("ticket", "na")

    payload = {**record, "account": acct, "regime": reg}
    pnl_s = f"{pnl:+.2f}" if isinstance(pnl, (int, float)) else "—"
    tags = ["intellitrade", "trade", acct.lower(), str(asset).lower(),
            reg.get("trend", "").lower(), reg.get("volatility", "").lower() + "vol"]
    md = (
        "---\n"
        f"type: trade\n"
        f"account: {acct}\n"
        f"asset: {asset}\n"
        f"strategy: {strat}\n"
        f"outcome: {outcome}\n"
        f"pnl: {pnl if isinstance(pnl, (int, float)) else 'null'}\n"
        f"regime: \"{reg.get('label', 'Unknown')}\"\n"
        f"adx: {reg.get('adx')}\n"
        f"atr_pct: {reg.get('atr_pct')}\n"
        f"ema_slope_pct: {reg.get('ema_slope_pct')}\n"
        f"closed_at: {closed}\n"
        "tags:\n" + "".join(f"  - {t}\n" for t in tags if t) +
        f"created: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
        "---\n\n"
        f"# {asset} {strat} — {outcome} {pnl_s} ({acct})\n\n"
        f"Regime at trade: **{reg.get('label', 'Unknown')}** "
        f"(ADX {reg.get('adx')}, ATR {reg.get('atr_pct')}%).\n"
        f"Entry {record.get('entry')} → close {record.get('close_price')} "
        f"(SL {record.get('sl')} / TP {record.get('tp')}).\n\n"
        "```json\n" + json.dumps(payload, indent=2, default=str) + "\n```\n"
    )
    date = str(closed)[:10].replace("-", "")
    path = os.path.join(settings.obsidian_trades_dir, f"trade_{date}_{asset}_{ticket}.md")
    ok = _write(path, md)
    if ok:
        log.info("Exported trade %s to vault (%s).", ticket, reg.get("label"))
    return ok


# ── Weekly backtest snapshot ──────────────────────────────────────────────────
def snapshot_backtests(timeframe: str = "H1", count: int = 2000,
                       source: str = "mt5") -> dict:
    """Run all strategies × assets, tag each asset's current regime, and write a
    snapshot to the vault. Returns a summary dict (also used by the API)."""
    from app.backtest.engine import run_backtest
    from app.core.constants import SUPPORTED_ASSETS, default_commission_per_lot
    from app.services import market_data
    from app.strategies.registry import build_strategy, list_strategies

    if not settings.obsidian_autolog_enabled or not settings.obsidian_backtests_dir:
        return {"ok": False, "error": "Obsidian autolog disabled or path unset."}

    strats = list_strategies()
    grid: dict[str, dict] = {}
    regimes: dict[str, dict] = {}
    for asset in SUPPORTED_ASSETS:
        df = market_data.get_ohlcv(asset, timeframe, count, source)
        regimes[asset] = (regime.classify(df) if df is not None and len(df)
                          else {"label": "Unknown"})
        grid[asset] = {}
        per_lot = default_commission_per_lot(asset)
        if df is None or len(df) == 0:
            for st in strats:
                grid[asset][st] = {"error": "no data"}
            continue
        for st in strats:
            r = run_backtest(df, build_strategy(st), asset, 10_000.0,
                             commission_per_lot=per_lot, timeframe=timeframe)
            m = r.metrics
            grid[asset][st] = {
                "return_pct": m["total_return_pct"], "win_rate_pct": m["win_rate_pct"],
                "profit_factor": m["profit_factor"], "max_dd_pct": m["max_drawdown_pct"],
                "trades": m["total_trades"],
            }

    now = datetime.now(timezone.utc)
    payload = {"generated_at": now.isoformat(), "timeframe": timeframe, "bars": count,
               "source": source, "regimes": regimes, "grid": grid}

    # Markdown: one table per asset (regime in the heading) + the data block.
    lines = [
        "---", "type: backtest_snapshot", f"timeframe: {timeframe}",
        f"created: {now.isoformat(timespec='seconds')}",
        "tags:", "  - intellitrade", "  - backtest", "  - snapshot", "---", "",
        f"# Backtest snapshot — {now.date()} ({timeframe}, {count} bars)", "",
    ]
    for asset in SUPPORTED_ASSETS:
        lines.append(f"## {asset} — regime: {regimes[asset].get('label', 'Unknown')}")
        lines.append("| Strategy | Return% | Win% | PF | MaxDD% | Trades |")
        lines.append("|---|---|---|---|---|---|")
        for st in strats:
            c = grid[asset][st]
            if "error" in c:
                lines.append(f"| {st} | — | — | — | — | (no data) |")
            else:
                lines.append(f"| {st} | {c['return_pct']} | {c['win_rate_pct']} | "
                             f"{c['profit_factor']} | {c['max_dd_pct']} | {c['trades']} |")
        lines.append("")
    lines.append("```json")
    lines.append(json.dumps(payload, indent=2, default=str))
    lines.append("```")

    path = os.path.join(settings.obsidian_backtests_dir,
                        f"backtest_{now.strftime('%Y%m%d_%H%M')}.md")
    ok = _write(path, "\n".join(lines))
    log.info("Backtest snapshot %s (%s).", "written" if ok else "FAILED", path)
    return {"ok": ok, "path": path if ok else None, "regimes": regimes,
            "assets": list(SUPPORTED_ASSETS), "strategies": strats}
