"""Account info + the guarded DEMO/LIVE profile switch."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.services.account_state import account_state
from app.services.mt5_client import mt5_client

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/info")
def info() -> dict:
    acct = mt5_client.account_info()
    return {
        "connected": acct is not None,
        "active_account": account_state.active(),
        "allow_live": settings.allow_live,
        "has_live": settings.has_live,
        "verified_type": mt5_client.verify_account_type(),
        "account": acct,
    }


@router.get("/status")
def status() -> dict:
    return {
        "active_account": account_state.active(),
        "allow_live": settings.allow_live,
        "has_live": settings.has_live,
        "obsidian_vault": settings.obsidian_vault_path,
        "telegram_configured": settings.telegram_configured,
    }


class SwitchRequest(BaseModel):
    target: str  # "DEMO" | "LIVE"


@router.post("/switch")
def switch(req: SwitchRequest) -> dict:
    """Switch the active MT5 profile and reconnect. Switching to LIVE is hard-
    gated: it requires ALLOW_LIVE=true AND configured live credentials."""
    target = req.target.upper()
    if target not in ("DEMO", "LIVE"):
        return {"ok": False, "reason": "target must be DEMO or LIVE"}

    if target == "LIVE":
        if not settings.allow_live:
            return {"ok": False, "active_account": account_state.active(),
                    "reason": "Live blocked: set ALLOW_LIVE=true in .env to enable real-money."}
        if not settings.has_live:
            return {"ok": False, "active_account": account_state.active(),
                    "reason": "Live credentials not set (MT5_LIVE_LOGIN/PASSWORD/SERVER in .env)."}

    account_state.set(target)
    connected = mt5_client.reconnect()
    verified = mt5_client.verify_account_type()

    # Safety: if we asked for LIVE but the terminal didn't end up LIVE, revert.
    if target == "LIVE" and verified is not None and verified != "LIVE":
        account_state.set("DEMO")
        mt5_client.reconnect()
        return {"ok": False, "active_account": "DEMO",
                "reason": f"Terminal reported '{verified}', not LIVE — reverted to DEMO for safety."}

    return {
        "ok": connected,
        "active_account": account_state.active(),
        "verified_type": verified,
        "account": mt5_client.account_info(),
    }
