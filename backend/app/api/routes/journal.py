"""Journal entries — saved as Obsidian-friendly Markdown into the vault so the
RAG layer can later read your reflections, not just static rules.

Also reads entries back (parsing the YAML frontmatter we write) and produces a
deterministic monthly analysis: net P/L grouped by asset / session / tag so you
can see which areas are improving and which need work. An LLM-written narrative
diagnostic can be layered on top of this later."""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/journal", tags=["journal"])


class JournalEntry(BaseModel):
    date: str
    asset: str
    session: str
    pnl: float
    notes: str
    tags: list[str] = []


@router.post("/save")
def save(entry: JournalEntry) -> dict:
    target_dir = settings.obsidian_trades_dir
    if not target_dir:
        return {"status": "ERROR", "message": "OBSIDIAN_TRADES_DIR not set."}
    os.makedirs(target_dir, exist_ok=True)

    tags_yaml = "".join(f"\n  - {t}" for t in entry.tags)
    md = (
        f"---\n"
        f"date: {entry.date}\n"
        f"asset: {entry.asset}\n"
        f"session: {entry.session}\n"
        f"pnl: {entry.pnl}\n"
        f"tags:{tags_yaml}\n"
        f"created: {datetime.now().isoformat(timespec='seconds')}\n"
        f"---\n\n"
        f"# {entry.session} Session — {entry.asset}\n\n{entry.notes}\n"
    )
    safe = entry.date.replace("-", "")
    path = os.path.join(target_dir, f"{safe}_{entry.asset}.md")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        return {"status": "SUCCESS", "path": path}
    except Exception as exc:  # noqa: BLE001
        return {"status": "ERROR", "message": str(exc)}


@router.get("/entries")
def entries(limit: int = 50) -> dict:
    items = _read_all_entries()
    items.sort(key=lambda e: (e["date"], e["file"]), reverse=True)
    return {"count": len(items), "entries": items[:limit]}


@router.get("/analysis")
def analysis(month: str | None = None) -> dict:
    """Aggregate one month's entries (YYYY-MM; defaults to current month)."""
    month = month or date.today().strftime("%Y-%m")
    rows = [e for e in _read_all_entries() if e["date"].startswith(month)]

    if not rows:
        return {"month": month, "entries": 0, "message": "No entries for this month."}

    total_pnl = sum(r["pnl"] for r in rows)
    wins = [r for r in rows if r["pnl"] > 0]

    by_asset = _group(rows, "asset")
    by_session = _group(rows, "session")
    tag_counts: dict[str, int] = defaultdict(int)
    tag_pnl: dict[str, float] = defaultdict(float)
    for r in rows:
        for t in r["tags"]:
            tag_counts[t] += 1
            tag_pnl[t] += r["pnl"]

    best = max(rows, key=lambda r: r["pnl"])
    worst = min(rows, key=lambda r: r["pnl"])

    return {
        "month": month,
        "entries": len(rows),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / len(rows), 2),
        "win_rate_pct": round(len(wins) / len(rows) * 100, 2),
        "by_asset": by_asset,
        "by_session": by_session,
        "tags": sorted(
            ({"tag": t, "count": tag_counts[t], "pnl": round(tag_pnl[t], 2)}
             for t in tag_counts),
            key=lambda x: x["count"], reverse=True,
        ),
        "best": {"date": best["date"], "asset": best["asset"], "pnl": best["pnl"]},
        "worst": {"date": worst["date"], "asset": worst["asset"], "pnl": worst["pnl"]},
        "insights": _insights(by_asset, by_session),
    }


# ── helpers ──────────────────────────────────────────────────────────────────
def _read_all_entries() -> list[dict]:
    target_dir = settings.obsidian_trades_dir
    if not target_dir or not os.path.isdir(target_dir):
        return []
    out: list[dict] = []
    for name in os.listdir(target_dir):
        if not name.endswith(".md"):
            continue
        try:
            with open(os.path.join(target_dir, name), encoding="utf-8") as f:
                meta, notes = _parse_frontmatter(f.read())
        except Exception:  # noqa: BLE001 — skip unreadable/foreign notes
            continue
        out.append({
            "file": name,
            "date": str(meta.get("date", "")),
            "asset": str(meta.get("asset", "")),
            "session": str(meta.get("session", "")),
            "pnl": _to_float(meta.get("pnl")),
            "tags": meta.get("tags", []) if isinstance(meta.get("tags"), list) else [],
            "notes": notes,
        })
    return out


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Minimal YAML-frontmatter parser for the simple key: value (+ list) format
    we write. No external dependency."""
    meta: dict = {}
    notes = text.strip()
    if not text.startswith("---"):
        return meta, notes
    parts = text.split("---", 2)
    if len(parts) < 3:
        return meta, notes
    fm, body = parts[1], parts[2].strip()
    # drop the auto '# ... Session' heading line from the body
    lines = body.splitlines()
    if lines and lines[0].startswith("# "):
        body = "\n".join(lines[1:]).strip()

    list_key: str | None = None
    for line in fm.splitlines():
        if not line.strip():
            continue
        if line.startswith(("  - ", "- ")) and list_key:
            meta[list_key].append(line.split("-", 1)[1].strip())
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            if val == "":
                list_key = key
                meta[key] = []
            else:
                list_key = None
                meta[key] = val
    return meta, body


def _group(rows: list[dict], field: str) -> dict:
    agg: dict[str, dict] = {}
    for r in rows:
        key = r[field] or "—"
        g = agg.setdefault(key, {"count": 0, "pnl": 0.0, "wins": 0})
        g["count"] += 1
        g["pnl"] += r["pnl"]
        if r["pnl"] > 0:
            g["wins"] += 1
    for g in agg.values():
        g["pnl"] = round(g["pnl"], 2)
        g["win_rate_pct"] = round(g["wins"] / g["count"] * 100, 2)
    return agg


def _to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _insights(by_asset: dict, by_session: dict) -> list[str]:
    out: list[str] = []
    if by_asset:
        best = max(by_asset.items(), key=lambda kv: kv[1]["pnl"])
        worst = min(by_asset.items(), key=lambda kv: kv[1]["pnl"])
        out.append(f"Strongest asset: {best[0]} ({best[1]['pnl']:+.2f}).")
        if worst[1]["pnl"] < 0:
            out.append(f"Needs work: {worst[0]} ({worst[1]['pnl']:+.2f}) — review these setups.")
    if by_session:
        ws = min(by_session.items(), key=lambda kv: kv[1]["pnl"])
        if ws[1]["pnl"] < 0:
            out.append(f"Losing session: {ws[0]} ({ws[1]['pnl']:+.2f}) — consider a session filter.")
    return out
