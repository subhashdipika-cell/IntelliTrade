"""Persisted auto-scanner config — which assets/strategy/timeframe are 'deployed'
and whether the scanner runs and in which mode.

mode:
  - "alert_only"  : a passing setup sends a Telegram 'setup found' alert; no order.
  - "autonomous"  : a passing setup is executed automatically on the Demo account.

Starts disabled + alert_only so nothing trades itself until you opt in."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from threading import Lock

from app.core.logging_setup import get_logger

log = get_logger("services.scanner_settings")

_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
_PATH = os.path.join(_DATA_DIR, "scanner_settings.json")

VALID_MODES = ("alert_only", "autonomous")


@dataclass
class ScannerSettings:
    enabled: bool = False
    mode: str = "alert_only"
    assets: list[str] = field(default_factory=lambda: ["GOLD", "BTC", "ETH"])
    strategies: list[str] = field(default_factory=lambda: ["donchian_breakout"])
    timeframe: str = "H1"
    wiki_enabled: bool = True
    # Per-asset strategy selection — when an asset has an entry here it
    # OVERRIDES the global `strategies` list for that asset. Added 2026-07-05
    # after the 3000-bar H1 matrix backtest showed each asset has different
    # winners (e.g. macd_cross +21% on GOLD but -15% on BTC; rsi_reversion
    # +6.6% on ETH but -27.7% on GOLD). Empty dict = old behavior.
    strategies_by_asset: dict = field(default_factory=dict)


class ScannerStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._s = self._load()

    def _load(self) -> ScannerSettings:
        if os.path.exists(_PATH):
            try:
                with open(_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                # migrate old single-strategy field to the list form
                if "strategy" in data and "strategies" not in data:
                    data["strategies"] = [data["strategy"]]
                allowed = {f.name for f in fields(ScannerSettings)}
                return ScannerSettings(**{k: v for k, v in data.items() if k in allowed})
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not load scanner settings, using defaults: %s", exc)
        return ScannerSettings()

    def get(self) -> ScannerSettings:
        with self._lock:
            return ScannerSettings(**asdict(self._s))

    def update(self, **patch) -> ScannerSettings:
        allowed = {f.name for f in fields(ScannerSettings)}
        with self._lock:
            for k, v in patch.items():
                if k not in allowed or v is None:
                    continue
                if k == "mode" and v not in VALID_MODES:
                    continue
                setattr(self._s, k, v)
            os.makedirs(_DATA_DIR, exist_ok=True)
            with open(_PATH, "w", encoding="utf-8") as f:
                json.dump(asdict(self._s), f, indent=2)
            log.info("Scanner settings saved: enabled=%s mode=%s", self._s.enabled, self._s.mode)
            return ScannerSettings(**asdict(self._s))


scanner_settings = ScannerStore()
