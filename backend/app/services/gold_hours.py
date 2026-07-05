"""Friday gold cutoff (IST) — protects against Vantage's early Friday closes.

Vantage XAUUSD+ hours, verified from actual M1 bar data (server = UTC+3):
daily open 03:30 IST, close 02:27 IST next day. Normal Fridays run the full
session (close ~02:26 IST Sat) — but US-HOLIDAY Fridays (Juneteenth 19-Jun-26,
July-4th-observed 3-Jul-26) closed at 22:29 IST with no warning. Being caught
in a position then means holding through a 2.5-day weekend gap.

Rule: gold goes flat before 22:30 IST EVERY Friday — new entries are blocked
from 21:45 IST (Risk stage) and open positions are flattened at 22:15 IST
(trade monitor). Worst case we skip the thin US afternoon; best case we dodge
the weekend gap.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
BLOCK_MIN = 21 * 60 + 45     # 21:45 IST Friday — no new gold entries
FLATTEN_MIN = 22 * 60 + 15   # 22:15 IST Friday — close open gold positions


def is_gold(asset_or_symbol: str) -> bool:
    s = (asset_or_symbol or "").upper()
    return "XAU" in s or "GOLD" in s


def friday_state() -> tuple[bool, bool]:
    """(block_new_entries, flatten_open) for the Friday gold cutoff, in IST."""
    ist = datetime.now(IST)
    if ist.weekday() != 4:   # Friday only
        return False, False
    mins = ist.hour * 60 + ist.minute
    return mins >= BLOCK_MIN, mins >= FLATTEN_MIN
