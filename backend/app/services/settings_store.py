"""Persisted money-management settings — the single source of truth for risk.

These are the lot size / daily-loss / RR / override values set on the Money Mgmt
page. They persist to a JSON file so they survive restarts, and the Risk pipeline
stage reads them via the factory (see app/pipeline/factory.py). The Live page no
longer carries per-run risk inputs — it uses whatever is saved here."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from threading import Lock

from app.core.constants import SUPPORTED_ASSETS
from app.core.logging_setup import get_logger

log = get_logger("services.settings")

_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
_SETTINGS_PATH = os.path.join(_DATA_DIR, "money_settings.json")


def _default_lots() -> dict[str, float]:
    # Per-asset lot size — 0.10 lots is very different exposure across assets
    # (GOLD 1 lot = 100oz, BTC/ETH 1 lot = 1 coin), so each is set separately.
    return {a: 0.10 for a in SUPPORTED_ASSETS}


@dataclass
class MoneySettings:
    # Per-asset lot sizes; `base_lots` is the fallback for any asset not listed.
    lots_by_asset: dict[str, float] = field(default_factory=_default_lots)
    base_lots: float = 0.10
    risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 2.0
    rr_ratio: str = "1:2"
    max_open_trades: int = 3
    hard_stop_override: bool = False

    # ── Trailing stop (profit protection) ────────────────────────────────────
    # Triggers are % of the distance from entry to target (RR-agnostic, so they
    # still arm even when a trade's RR < 1). Trail distances are in units of the
    # initial risk R = |entry - initial_SL|, so we never need to refetch ATR.
    trailing_enabled: bool = True
    be_trigger_pct: float = 50.0       # move SL → breakeven once price travels this far to TP
    be_buffer_r: float = 0.10          # breakeven offset (× R) to cover spread + commission
    trail_trigger_pct: float = 65.0    # beyond this, SL trails the best price
    trail_r_mult: float = 0.70         # stage-2 give-back distance (× R)
    near_target_pct: float = 80.0      # "near target" zone — tighten hard here
    near_target_r_mult: float = 0.30   # stage-3 give-back distance (× R)

    # ── Daily profit lock ────────────────────────────────────────────────────
    # Once today's realised P&L reaches the target, STOP opening new positions
    # for the rest of the day (open trades keep trailing/managing). The
    # give-back stop locks earlier when a good day starts bleeding back into
    # fresh trades' SLs: it arms once the day peaks at ≥ half the target.
    profit_lock_enabled: bool = True
    profit_lock_pct: float = 1.0       # lock at +N% of balance realised today (0 = off)
    profit_giveback_pct: float = 50.0  # lock when day P&L falls this % from its peak (0 = off)

    # ── Structure-aware target ───────────────────────────────────────────────
    # Cap a signal's target just below the nearest swing resistance (longs) /
    # support (shorts) so we don't aim past a level price is unlikely to break.
    target_cap_enabled: bool = True
    resistance_lookback: int = 20      # bars scanned for the swing level
    min_rr_after_cap: float = 1.2      # RR floor after capping
    skip_low_rr: bool = False          # if True, BLOCK signals whose capped RR < floor


class SettingsStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._settings = self._load()

    def _load(self) -> MoneySettings:
        if os.path.exists(_SETTINGS_PATH):
            try:
                with open(_SETTINGS_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                allowed = {f.name for f in fields(MoneySettings)}
                s = MoneySettings(**{k: v for k, v in data.items() if k in allowed})
                return _normalize(s)
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not load money settings, using defaults: %s", exc)
        return MoneySettings()

    def get(self) -> MoneySettings:
        with self._lock:
            return MoneySettings(**asdict(self._settings))

    def update(self, **patch) -> MoneySettings:
        allowed = {f.name for f in fields(MoneySettings)}
        with self._lock:
            for k, v in patch.items():
                if k in allowed and v is not None:
                    setattr(self._settings, k, v)
            _normalize(self._settings)
            self._persist()
            return MoneySettings(**asdict(self._settings))

    def _persist(self) -> None:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self._settings), f, indent=2)
        log.info("Money settings saved to %s", _SETTINGS_PATH)


def _normalize(s: MoneySettings) -> MoneySettings:
    """Guarantee `lots_by_asset` carries every supported asset (filling any gap
    from `base_lots`), so old configs and partial UI patches stay complete."""
    lots = dict(s.lots_by_asset or {})
    for a in SUPPORTED_ASSETS:
        lots[a] = float(lots.get(a, s.base_lots))
    s.lots_by_asset = lots
    return s


money_settings = SettingsStore()
