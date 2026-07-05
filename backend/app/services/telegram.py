"""Telegram alerts via the Bot API.

Every alert opens with an app-name banner (`settings.app_name`, default
"IntelliTrade") so its messages are distinguishable from the other MT5 bots that
post to the same chat.

Two alerts as specified:
  • ENTRY  — asset, entry price, SL, target, capital deployed, total capital
  • EXIT   — asset, outcome (SL / TSL / TGT), PROFIT/LOSS in $, total capital after

Design notes:
  - Failures NEVER raise into the trading pipeline. A dead Telegram bot must not
    stop a trade from being placed or monitored — we log and move on.
  - Uses MarkdownV2; all dynamic text is escaped.
"""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.constants import to_terminal_symbol
from app.core.logging_setup import get_logger
from app.pipeline.context import Outcome, Signal, TradeContext

log = get_logger("services.telegram")

_API = "https://api.telegram.org/bot{token}/sendMessage"
_TIMEOUT = 8.0

# MarkdownV2 reserved characters that must be escaped.
_MDV2_SPECIALS = r"_*[]()~`>#+-=|{}.!"


def _esc(value: object) -> str:
    text = str(value)
    return "".join("\\" + ch if ch in _MDV2_SPECIALS else ch for ch in text)


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{settings.base_currency} {value:,.2f}"


def _header(title: str) -> list[str]:
    """App-name banner so this bot's alerts are distinguishable from the other
    MT5 apps that post to the same Telegram chat. Stamped on every alert."""
    return [f"🤖 *{_esc(settings.app_name)}*", title, ""]


def _send(text: str) -> bool:
    """Fire-and-forget send. Returns True on success, never raises."""
    if not settings.telegram_enabled:
        log.info("Telegram disabled; skipping alert.")
        return False
    if not settings.telegram_configured:
        log.warning("Telegram token/chat id not set; skipping alert.")
        return False
    try:
        resp = httpx.post(
            _API.format(token=settings.telegram_bot_token),
            json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": True,
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            log.warning("Telegram API %s: %s", resp.status_code, resp.text)
            return False
        return True
    except Exception as exc:  # noqa: BLE001 — alerts must never break trading
        log.warning("Telegram send failed: %s", exc)
        return False


# ── Entry alert ──────────────────────────────────────────────────────────────
def send_entry_alert(
    signal: Signal,
    capital_deployed: float,
    total_capital: float,
) -> bool:
    symbol = to_terminal_symbol(signal.asset)
    arrow = "🟢 BUY" if signal.direction.value == "BUY" else "🔴 SELL"
    rr = _risk_reward(signal)

    lines = _header(f"*📈 TRADE OPENED \\— {arrow}*") + [
        f"*Asset:* `{_esc(symbol)}`  \\({_esc(signal.asset)}\\)",
        f"*Entry:* `{_esc(f'{signal.entry:g}')}`",
        f"*Stop Loss:* `{_esc(f'{signal.stop_loss:g}')}`",
        f"*Target:* `{_esc(f'{signal.target:g}')}`",
        f"*R:R:* `{_esc(rr)}`",
        "",
        f"*Capital Deployed:* `{_esc(_money(capital_deployed))}`",
        f"*Total Capital:* `{_esc(_money(total_capital))}`",
    ]
    if signal.lots:
        lines.insert(7, f"*Lots:* `{_esc(f'{signal.lots:g}')}`")
    return _send("\n".join(lines))


# ── Setup-found alert (scanner, alert-only mode) ─────────────────────────────
def send_setup_alert(signal: Signal, capital_deployed: float | None,
                     total_capital: float | None) -> bool:
    symbol = to_terminal_symbol(signal.asset)
    arrow = "🟢 BUY" if signal.direction.value == "BUY" else "🔴 SELL"
    lines = _header(f"*🔔 SETUP FOUND \\— {arrow}*  _\\(alert only\\)_") + [
        f"*Asset:* `{_esc(symbol)}`  \\({_esc(signal.asset)}\\)",
        f"*Entry:* `{_esc(f'{signal.entry:g}')}`",
        f"*Stop Loss:* `{_esc(f'{signal.stop_loss:g}')}`",
        f"*Target:* `{_esc(f'{signal.target:g}')}`",
        f"*R:R:* `{_esc(_risk_reward(signal))}`",
        "",
        "_Autonomous execution is OFF — review and place manually if you agree._",
    ]
    return _send("\n".join(lines))


# ── Exit alert ───────────────────────────────────────────────────────────────
_OUTCOME_BADGE = {
    Outcome.TGT: "🎯 TARGET HIT",
    Outcome.SL: "🛑 STOP LOSS",
    Outcome.TSL: "🪤 TRAILING STOP",
    Outcome.MANUAL: "✋ MANUAL CLOSE",
}


def send_exit_alert(
    asset: str,
    outcome: Outcome,
    final_capital: float,
    pnl: float | None = None,
) -> bool:
    symbol = to_terminal_symbol(asset)
    badge = _OUTCOME_BADGE.get(outcome, _esc(outcome.value))
    lines = _header(f"*📉 TRADE CLOSED \\— {badge}*") + [
        f"*Asset:* `{_esc(symbol)}`  \\({_esc(asset)}\\)",
        f"*Outcome:* `{_esc(outcome.value)}`",
    ]
    if pnl is not None:
        # Spell out PROFIT / LOSS in $ with a signed amount — no ambiguity.
        word = "🟢 PROFIT" if pnl >= 0 else "🔴 LOSS"
        signed = f"{'+' if pnl >= 0 else '-'}{_money(abs(pnl))}"
        lines.append(f"*Result:* {word}  `{_esc(signed)}`")
    lines += [
        "",
        f"*Total Capital After Trade:* `{_esc(_money(final_capital))}`",
    ]
    return _send("\n".join(lines))


# ── Convenience wrappers that read straight off a TradeContext ────────────────
def alert_from_context_entry(ctx: TradeContext) -> bool:
    if ctx.signal is None or ctx.capital_deployed is None or ctx.total_capital is None:
        log.warning("Entry alert skipped: context missing signal/capital fields.")
        return False
    return send_entry_alert(ctx.signal, ctx.capital_deployed, ctx.total_capital)


def alert_from_context_exit(ctx: TradeContext, pnl: float | None = None) -> bool:
    if ctx.final_capital is None:
        log.warning("Exit alert skipped: context missing final_capital.")
        return False
    return send_exit_alert(ctx.asset, ctx.outcome, ctx.final_capital, pnl)


def _risk_reward(signal: Signal) -> str:
    risk = abs(signal.entry - signal.stop_loss)
    reward = abs(signal.target - signal.entry)
    if risk == 0:
        return "n/a"
    return f"1:{reward / risk:.2f}"
