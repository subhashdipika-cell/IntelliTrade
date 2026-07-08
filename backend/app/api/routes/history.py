"""Closed-trade history + monthly summary, read from the append-only store."""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime, timezone

from fastapi import APIRouter

from app.core.config import settings
from app.services.history_store import history_store

router = APIRouter(prefix="/history", tags=["history"])


@router.get("/trades")
def trades(limit: int = 100) -> dict:
    rows = history_store.all()
    rows.sort(key=lambda r: r.get("closed_at") or "", reverse=True)
    return {"count": len(rows), "trades": rows[:limit]}


@router.get("/strategy-matrix")
def strategy_matrix(month: str | None = None) -> dict:
    """Per-strategy × per-asset scoreboard from closed trades — answers 'which
    strategy works for which asset, which is useless'. Defaults to all-time."""
    rows = history_store.all()
    if month:
        rows = [r for r in rows if (r.get("closed_at") or "").startswith(month)]
    if not rows:
        return {"month": month or "all", "trades": 0,
                "message": "No closed trades yet — let the scanner run."}

    strategies = sorted({r.get("strategy") or "—" for r in rows})
    assets = sorted({r.get("asset") or "—" for r in rows})

    def cell() -> dict:
        return {"count": 0, "pnl": 0.0, "wins": 0}

    def finalize(c: dict) -> dict:
        c["pnl"] = round(c["pnl"], 2)
        c["win_rate_pct"] = round(c["wins"] / c["count"] * 100, 2) if c["count"] else 0.0
        return c

    matrix = {st: {a: cell() for a in assets} for st in strategies}
    totals = {st: cell() for st in strategies}
    for r in rows:
        st = r.get("strategy") or "—"
        a = r.get("asset") or "—"
        pnl = r.get("pnl", 0.0)
        for tgt in (matrix[st][a], totals[st]):
            tgt["count"] += 1
            tgt["pnl"] += pnl
            if pnl > 0:
                tgt["wins"] += 1

    return {
        "month": month or "all",
        "trades": len(rows),
        "strategies": strategies,
        "assets": assets,
        "matrix": {st: {a: finalize(matrix[st][a]) for a in assets} for st in strategies},
        "totals": {st: finalize(totals[st]) for st in strategies},
    }


def _trade_metrics(rows: list[dict]) -> dict:
    """Full analytics for a set of closed trades."""
    n = len(rows)
    if n == 0:
        return {"trades": 0}
    pnls = [r.get("pnl", 0.0) for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    net = sum(pnls)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0  # negative

    # Max drawdown over the month's equity curve (ordered by close time).
    ordered = sorted(rows, key=lambda r: r.get("closed_at") or "")
    cum = peak = max_dd = 0.0
    cur_w = cur_l = max_w = max_l = 0
    for r in ordered:
        p = r.get("pnl", 0.0)
        cum += p
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)
        if p > 0:
            cur_w, cur_l = cur_w + 1, 0
            max_w = max(max_w, cur_w)
        elif p < 0:
            cur_l, cur_w = cur_l + 1, 0
            max_l = max(max_l, cur_l)

    # Planned R:R from entry/sl/tp where available.
    rrs = []
    for r in rows:
        e, sl, tp = r.get("entry"), r.get("sl"), r.get("tp")
        if e and sl and tp and abs(e - sl) > 0:
            rrs.append(abs(tp - e) / abs(e - sl))

    by_outcome: dict[str, int] = defaultdict(int)
    for r in rows:
        by_outcome[r.get("outcome", "?")] += 1

    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / n * 100, 2),
        "net_pnl": round(net, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else None,
        "expectancy": round(net / n, 2),                          # avg P/L per trade
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "payoff_ratio": round(avg_win / abs(avg_loss), 2) if avg_loss else None,  # realised R:R
        "avg_planned_rr": round(sum(rrs) / len(rrs), 2) if rrs else None,
        "best_trade": round(max(pnls), 2),
        "worst_trade": round(min(pnls), 2),
        "max_drawdown": round(max_dd, 2),
        "max_win_streak": max_w,
        "max_loss_streak": max_l,
        "by_outcome": dict(by_outcome),
    }


@router.get("/monthly-report")
def monthly_report(month: str | None = None) -> dict:
    """End-of-month analytics: overall + per-strategy (win rate, profit factor,
    R:R, drawdown, best/worst trade, streaks, outcomes), ranked best→worst."""
    month = month or date.today().strftime("%Y-%m")
    rows = [r for r in history_store.all() if (r.get("closed_at") or "").startswith(month)]
    if not rows:
        return {"month": month, "trades": 0, "message": "No closed trades this month."}

    strategies = sorted({r.get("strategy") or "—" for r in rows})
    by_strategy = {
        st: _trade_metrics([r for r in rows if (r.get("strategy") or "—") == st])
        for st in strategies
    }
    ranking = sorted(strategies, key=lambda s: by_strategy[s]["net_pnl"], reverse=True)
    return {
        "month": month,
        "overall": _trade_metrics(rows),
        "by_strategy": by_strategy,
        "ranking": ranking,
    }


@router.get("/summary")
def summary(month: str | None = None) -> dict:
    """Aggregate closed trades for a month (YYYY-MM; defaults to current)."""
    month = month or date.today().strftime("%Y-%m")
    rows = [r for r in history_store.all() if (r.get("closed_at") or "").startswith(month)]
    if not rows:
        return {"month": month, "trades": 0, "message": "No closed trades this month."}

    total_pnl = sum(r.get("pnl", 0.0) for r in rows)
    wins = [r for r in rows if r.get("pnl", 0.0) > 0]

    by_outcome: dict[str, int] = defaultdict(int)
    by_asset: dict[str, dict] = {}
    for r in rows:
        by_outcome[r.get("outcome", "?")] += 1
        a = by_asset.setdefault(r.get("asset", "—"), {"count": 0, "pnl": 0.0, "wins": 0})
        a["count"] += 1
        a["pnl"] += r.get("pnl", 0.0)
        if r.get("pnl", 0.0) > 0:
            a["wins"] += 1
    for a in by_asset.values():
        a["pnl"] = round(a["pnl"], 2)
        a["win_rate_pct"] = round(a["wins"] / a["count"] * 100, 2)

    ending = next((r.get("final_capital") for r in rows if r.get("final_capital") is not None), None)
    return {
        "month": month,
        "trades": len(rows),
        "total_pnl": round(total_pnl, 2),
        "win_rate_pct": round(len(wins) / len(rows) * 100, 2),
        "by_outcome": dict(by_outcome),
        "by_asset": by_asset,
        "ending_capital": ending,
    }


# ── Obsidian monthly export ───────────────────────────────────────────────────
def _session_for(iso_ts: str | None) -> str:
    """Global trading session for a UTC timestamp (IntelliTrade trades 24h
    markets — Gold / crypto — so forex sessions apply)."""
    if not iso_ts:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return "Unknown"
    h = dt.astimezone(timezone.utc).hour
    if h < 7:
        return "Asian"
    if h < 12:
        return "London"
    if h < 16:
        return "London/NY overlap"
    if h < 21:
        return "New York"
    return "Late US"


def _mdcell(v) -> str:
    return str("—" if v in (None, "") else v).replace("|", "/").replace("\n", " ")


def _group(rows: list[dict], key_fn) -> list[dict]:
    g: dict[str, dict] = {}
    for r in rows:
        k = key_fn(r) or "—"
        x = g.setdefault(k, {"n": 0, "w": 0, "pnl": 0.0})
        x["n"] += 1
        if r.get("pnl", 0.0) > 0:
            x["w"] += 1
        x["pnl"] += r.get("pnl", 0.0)
    return sorted(
        ({"label": k, "n": v["n"],
          "win": (v["w"] / v["n"] * 100) if v["n"] else 0.0, "pnl": v["pnl"]}
         for k, v in g.items()),
        key=lambda d: d["pnl"], reverse=True,
    )


def _monthly_markdown(month: str, rows: list[dict], overall: dict) -> str:
    def sess(r):
        return _session_for(r.get("opened_at") or r.get("closed_at"))

    money = lambda v: f"{'+' if v >= 0 else '-'}${abs(v):,.2f}"
    pct = lambda v: f"{v:.0f}%"
    yr, mo = month.split("-")
    month_name = datetime(int(yr), int(mo), 1).strftime("%B")

    def grp_table(title, rows_):
        out = f"\n## By {title}\n\n| {title[:1].upper() + title[1:]} | Trades | Win% | Net P&L |\n|---|---|---|---|\n"
        for r in rows_:
            out += f"| {_mdcell(r['label'])} | {r['n']} | {pct(r['win'])} | {money(r['pnl'])} |\n"
        return out

    tags = "".join(f"\n  - {t}" for t in ("intellitrade", "monthly", "trades", month))
    md = (
        f"---\ntype: monthly-trade-summary\napp: intellitrade\nmonth: {month}\n"
        f"generated: {datetime.now().isoformat(timespec='seconds')}\n"
        f"trades: {overall['trades']}\nwins: {overall.get('wins', 0)}\nlosses: {overall.get('losses', 0)}\n"
        f"win_rate: {overall.get('win_rate_pct', 0)}\nnet_pnl: {overall.get('net_pnl', 0)}\n"
        # net_usd: unified cross-app money field (IntelliTrade trades Vantage in USD,
        # so net_pnl already IS USD). Lets the vault dashboard compare all apps.
        f"net_usd: {overall.get('net_pnl', 0)}\n"
        f"profit_factor: {overall.get('profit_factor')}\nmax_drawdown: {overall.get('max_drawdown', 0)}\n"
        f"tags:{tags}\n---\n\n"
    )
    md += f"# IntelliTrade — {month_name} {yr} Trade Summary\n\n"
    md += (f"**{overall['trades']} trades** · {overall.get('wins', 0)}W / {overall.get('losses', 0)}L · "
           f"**{overall.get('win_rate_pct', 0):.1f}% win** · net **{money(overall.get('net_pnl', 0))}** · "
           f"PF {overall.get('profit_factor') if overall.get('profit_factor') is not None else '—'} · "
           f"max DD {money(overall.get('max_drawdown', 0))}\n")
    md += "\n> P&L is broker-realized (MT5 closed trades), net of spread & commission.\n"
    md += grp_table("session", _group(rows, sess))
    md += grp_table("strategy", _group(rows, lambda r: r.get("strategy")))
    md += grp_table("asset", _group(rows, lambda r: r.get("asset")))
    md += ("\n## Trades\n\n| Closed (UTC) | Session | Asset | Strategy | Dir | Lots | Outcome | P&L |\n"
           "|---|---|---|---|---|---|---|---|\n")
    for r in sorted(rows, key=lambda x: x.get("closed_at") or ""):
        md += (f"| {_mdcell((r.get('closed_at') or '')[:16].replace('T', ' '))} | {_mdcell(sess(r))} | "
               f"{_mdcell(r.get('asset'))} | {_mdcell(r.get('strategy'))} | {_mdcell(r.get('direction'))} | "
               f"{_mdcell(r.get('lots'))} | {_mdcell(r.get('outcome'))} | {money(r.get('pnl', 0.0))} |\n")
    md += "\n_Generated by IntelliTrade for Obsidian ingestion._\n"
    return md


@router.post("/monthly-export")
def monthly_export(month: str | None = None) -> dict:
    """Write the month's closed-trade rollup to the Obsidian vault
    (``<obsidian_trades_dir>/intellitrade/<YYYY-MM>.md``) with a per-trade session
    column and session/strategy/asset breakdowns, for later analysis."""
    month = month or date.today().strftime("%Y-%m")
    base = settings.obsidian_trades_dir
    if not base:
        return {"status": "ERROR", "message": "obsidian_trades_dir not set."}
    rows = [r for r in history_store.all() if (r.get("closed_at") or "").startswith(month)]
    if not rows:
        return {"status": "EMPTY", "month": month, "message": "No closed trades this month."}

    md = _monthly_markdown(month, rows, _trade_metrics(rows))
    folder = os.path.join(base, "intellitrade")
    try:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{month}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        return {"status": "SUCCESS", "month": month, "trades": len(rows), "path": path}
    except OSError as exc:
        return {"status": "ERROR", "message": str(exc)}
