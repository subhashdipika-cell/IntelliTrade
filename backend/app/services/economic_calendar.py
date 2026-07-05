"""Economic calendar via the free ForexFactory weekly JSON feed.

The free feed rate-limits (HTTP 429) if polled often, so this:
  - caches the raw feed to disk and refetches at most every 6h,
  - on a failed refetch (429/network) serves the last good data (stale) instead
    of blanking the ticker,
  - backs off so it never hammers the feed.

Datetimes are returned as the feed's ISO strings (with offset); the frontend
formats them to IST, so the backend needs no tz database."""
from __future__ import annotations

import json
import os
import time

import httpx

from app.core.logging_setup import get_logger

log = get_logger("services.calendar")

_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_TTL = 6 * 3600        # consider cache fresh for 6h
_MIN_RETRY = 900       # after a failure, wait 15m before trying again
_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
_CACHE_PATH = os.path.join(_DATA_DIR, "calendar_cache.json")

_mem: dict = {"at": 0.0, "raw": None, "last_try": 0.0}


def _load_disk() -> None:
    if _mem["raw"] is not None:
        return
    try:
        with open(_CACHE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        _mem["at"] = float(d.get("at", 0.0))
        _mem["raw"] = d.get("raw", [])
    except Exception:  # noqa: BLE001
        _mem["raw"] = []


def _save_disk() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump({"at": _mem["at"], "raw": _mem["raw"]}, f)


def _fetch_raw() -> list[dict]:
    resp = httpx.get(_URL, timeout=15.0, headers={"User-Agent": "IntelliTrade/1.0"})
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def _ensure_data() -> None:
    _load_disk()
    now = time.time()
    if _mem["raw"] and now - _mem["at"] < _TTL:
        return  # fresh
    if _mem["raw"] and now - _mem["last_try"] < _MIN_RETRY:
        return  # recently tried & failed — serve stale, don't hammer
    _mem["last_try"] = now
    try:
        _mem["raw"] = _fetch_raw()
        _mem["at"] = now
        _save_disk()
        log.info("Economic calendar refreshed (%d rows).", len(_mem["raw"]))
    except Exception as exc:  # noqa: BLE001 — keep serving stale data
        log.warning("Economic calendar fetch failed (serving cached): %s", exc)


def get_events(impact: str = "High", currencies: tuple[str, ...] = ("USD",)) -> dict:
    _ensure_data()
    raw = _mem["raw"] or []
    if not raw:
        return {"events": [], "count": 0, "error": "calendar feed unavailable"}

    want = impact.lower() if impact else ""
    out: list[dict] = []
    for e in raw:
        if want and str(e.get("impact", "")).lower() != want:
            continue
        if currencies and str(e.get("country", "")).upper() not in currencies:
            continue
        out.append({
            "title": e.get("title"),
            "country": e.get("country"),
            "impact": e.get("impact"),
            "iso": e.get("date"),
            "forecast": e.get("forecast"),
            "previous": e.get("previous"),
        })
    out.sort(key=lambda x: x["iso"] or "")
    return {
        "events": out,
        "count": len(out),
        "stale": bool(_mem["at"]) and time.time() - _mem["at"] > _TTL,
    }
