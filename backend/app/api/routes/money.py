"""Money management — live account figures + persisted risk settings.

The settings here are the single source of truth for the Risk pipeline stage
(read via the factory). Saving them affects every subsequent signal run."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.services.account_state import account_state
from app.services.daily_stats import daily_realized_stats
from app.services.mt5_client import mt5_client
from app.services.settings_store import money_settings
from app.services.trade_store import open_trades

router = APIRouter(prefix="/money", tags=["money"])


class SettingsPatch(BaseModel):
    base_lots: float | None = None
    lots_by_asset: dict[str, float] | None = None
    risk_per_trade_pct: float | None = None
    max_daily_loss_pct: float | None = None
    rr_ratio: str | None = None
    max_open_trades: int | None = None
    hard_stop_override: bool | None = None
    # Trailing stop
    trailing_enabled: bool | None = None
    be_trigger_pct: float | None = None
    be_buffer_r: float | None = None
    trail_trigger_pct: float | None = None
    trail_r_mult: float | None = None
    near_target_pct: float | None = None
    near_target_r_mult: float | None = None
    # Daily profit lock
    profit_lock_enabled: bool | None = None
    profit_lock_pct: float | None = None
    profit_giveback_pct: float | None = None
    # Structure-aware target
    target_cap_enabled: bool | None = None
    resistance_lookback: int | None = None
    min_rr_after_cap: float | None = None
    skip_low_rr: bool | None = None


@router.get("/overview")
def overview() -> dict:
    acct = mt5_client.account_info()
    drawdown = None
    if acct and acct.get("balance"):
        drawdown = round((acct["equity"] - acct["balance"]) / acct["balance"] * 100, 2)
    s = money_settings.get()
    daily = daily_realized_stats()
    # Mirror the Risk stage's profit-lock decision so the UI can show LOCKED.
    lock = {"active": False, "reason": "", "target": None}
    bal = daily.get("balance")
    if s.profit_lock_enabled and s.profit_lock_pct > 0 and bal:
        target = round(bal * s.profit_lock_pct / 100.0, 2)
        lock["target"] = target
        if daily["pnl"] >= target:
            lock.update(active=True, reason=f"Day banked: +{daily['pnl']:.2f} ≥ +{target:.2f}")
        elif (s.profit_giveback_pct > 0 and daily["peak"] >= target / 2
              and daily["pnl"] <= daily["peak"] * (1 - s.profit_giveback_pct / 100.0)):
            lock.update(active=True,
                        reason=f"Give-back stop: peaked +{daily['peak']:.2f}, now +{daily['pnl']:.2f}")
    return {
        "connected": acct is not None,
        "account": acct,
        "drawdown_pct": drawdown,
        "open_trades": len(open_trades),
        "active_account": account_state.active(),
        "allow_live": settings.allow_live,
        "has_live": settings.has_live,
        "settings": asdict(s),
        "daily": daily,
        "profit_lock": lock,
    }


@router.get("/settings")
def get_settings() -> dict:
    return asdict(money_settings.get())


@router.put("/settings")
def update_settings(patch: SettingsPatch) -> dict:
    updated = money_settings.update(**patch.model_dump(exclude_none=True))
    return asdict(updated)
