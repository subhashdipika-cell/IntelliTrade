"""Which MT5 profile (DEMO / LIVE) is currently active.

Session-only on purpose: it initialises from the .env default (`MT5_ACCOUNT_TYPE`)
and a restart reverts to that default. So a runtime switch to LIVE never silently
persists across restarts — a safety property for real-money mode."""
from __future__ import annotations

from threading import Lock

from app.core.config import settings


class AccountState:
    def __init__(self) -> None:
        self._lock = Lock()
        self._active = (settings.mt5_account_type or "DEMO").upper()

    def active(self) -> str:
        with self._lock:
            return self._active

    def set(self, account_type: str) -> str:
        with self._lock:
            self._active = "LIVE" if account_type.upper() == "LIVE" else "DEMO"
            return self._active

    def is_live(self) -> bool:
        return self.active() == "LIVE"


account_state = AccountState()
