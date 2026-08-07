"""Thin wrapper around the MetaTrader5 package.

Important safety property: `verify_account_type()` checks the LIVE terminal's
trade-mode against what config thinks it is. The executor calls this before any
order, so a real-money account can never be traded while the app believes it is
on Demo.

MetaTrader5 is Windows-only. On non-Windows machines (or before install) the
import fails and the client runs in a clearly-flagged stub mode so the rest of
the app and the backtester still work.
"""
from __future__ import annotations

import math
import os

import pandas as pd

from app.core.config import settings
from app.core.constants import to_terminal_symbol
from app.core.logging_setup import get_logger
from app.services.account_state import account_state

log = get_logger("services.mt5")

try:
    import MetaTrader5 as mt5  # type: ignore

    MT5_AVAILABLE = True
except Exception:  # noqa: BLE001
    mt5 = None  # type: ignore
    MT5_AVAILABLE = False
    log.warning("MetaTrader5 package not available — running in STUB mode.")

_TIMEFRAMES = {
    "M5": 5, "M15": 15, "M30": 30, "H1": 16385, "H4": 16388, "D1": 16408,
}  # mirror of mt5.TIMEFRAME_* constants to avoid import at module load

# Identifies IntelliTrade's orders in the terminal (lets you filter our trades).
_MAGIC = 770011

# ── MT5 server clock ─────────────────────────────────────────────────────────
# MT5 returns position/deal times as epoch seconds expressed in the BROKER'S
# server clock, not UTC. Vantage runs UTC+3, so feeding p.time straight into
# datetime.fromtimestamp(..., tz=timezone.utc) stamps every MT5-sourced trade
# three hours in the future. That is how three July 2026 trades ended up with
# closed_at BEFORE opened_at: opened_at came from MT5 (inflated +3h) while
# closed_at came from datetime.now(), so anything held under 3h inverted.
#
# The offset is MEASURED rather than assumed — brokers change it and DST
# shifts it — by comparing a live tick's timestamp against the wall clock.
# Cached for an hour; falls back to 0 (raw server time) if no symbol quotes,
# which is no worse than the previous behaviour.
_SRV_OFFSET: dict = {"at": 0.0, "sec": None}


def _server_offset_sec() -> int:
    """Seconds to SUBTRACT from an MT5 timestamp to get true UTC."""
    import time as _t

    if _SRV_OFFSET["sec"] is not None and _t.time() - _SRV_OFFSET["at"] < 3600:
        return _SRV_OFFSET["sec"]
    off = 0
    try:
        for sym in ("XAUUSD+", "BTCUSD", "EURUSD"):
            if mt5.symbol_select(sym, True):
                tick = mt5.symbol_info_tick(sym)
                if tick and tick.time:
                    off = int(round((tick.time - _t.time()) / 3600.0)) * 3600
                    break
    except Exception:
        off = 0
    _SRV_OFFSET.update(at=_t.time(), sec=off)
    return off


def mt5_ts_to_utc(ts) -> str:
    """MT5 server-clock epoch -> true-UTC ISO string."""
    from datetime import datetime, timezone

    return datetime.fromtimestamp(int(ts) - _server_offset_sec(),
                                  tz=timezone.utc).isoformat()


def _deal_reason_str(code) -> str:
    """Map an MT5 deal reason to a simple tag. 'SL' = stop-loss hit (NOT trailed),
    'TP' = take-profit, 'SO' = stop-out, else 'MANUAL'."""
    if not MT5_AVAILABLE:
        return "MANUAL"
    mapping = {
        mt5.DEAL_REASON_TP: "TP",
        mt5.DEAL_REASON_SL: "SL",
        getattr(mt5, "DEAL_REASON_SO", -99): "SO",
    }
    return mapping.get(code, "MANUAL")


class MT5Client:
    def __init__(self) -> None:
        self._connected = False

    def connect(self) -> bool:
        if not MT5_AVAILABLE:
            return False
        # Use the active profile's terminal (LIVE can have its own isolated
        # install). If the path is wrong/missing, fall back to attaching to an
        # already-running terminal (initialize() no-arg).
        path = settings.terminal_path_for(account_state.active())
        initialized = False
        if path and os.path.exists(path):
            initialized = mt5.initialize(path=path)
        if not initialized:
            initialized = mt5.initialize()
        if not initialized:
            log.error("MT5 initialize failed: %s", mt5.last_error())
            return False

        # Select the active profile (DEMO/LIVE) and its credentials.
        login, password, server = settings.credentials_for(account_state.active())

        # If the terminal is already logged into the desired account, use that
        # session as-is — re-calling login() on an active session can IPC-timeout.
        info = mt5.account_info()
        already = info is not None and (not login or info.login == login)
        if not already and login:
            ok = mt5.login(login=login, password=password, server=server)
            if not ok:
                log.error("MT5 login failed: %s", mt5.last_error())
                mt5.shutdown()
                return False
        self._connected = True
        return True

    def reconnect(self) -> bool:
        """Tear down and reconnect — used when switching DEMO/LIVE profiles."""
        self.shutdown()
        return self.connect()

    def shutdown(self) -> None:
        if MT5_AVAILABLE and self._connected:
            mt5.shutdown()
            self._connected = False

    def verify_account_type(self) -> str | None:
        """Returns 'DEMO' / 'LIVE' / 'CONTEST' as reported by the terminal, or
        None if unknown. The executor compares this against settings."""
        if not MT5_AVAILABLE or not self._connected:
            return None
        info = mt5.account_info()
        if info is None:
            return None
        # mt5.ACCOUNT_TRADE_MODE_DEMO = 0, REAL = 2, CONTEST = 1
        return {0: "DEMO", 1: "CONTEST", 2: "LIVE"}.get(info.trade_mode)

    def account_info(self) -> dict | None:
        if not MT5_AVAILABLE or not self._connected:
            return None
        info = mt5.account_info()
        if info is None:
            return None
        return {
            "balance": info.balance,
            "equity": info.equity,
            "margin_free": info.margin_free,
            "currency": info.currency,
        }

    def fetch_ohlcv(self, asset: str, timeframe: str = "H1", count: int = 2000) -> pd.DataFrame:
        symbol = to_terminal_symbol(asset)
        if not MT5_AVAILABLE or not self._connected:
            log.warning("fetch_ohlcv stub: returning empty frame for %s.", symbol)
            return pd.DataFrame(columns=["open", "high", "low", "close", "tick_volume"])
        tf = _TIMEFRAMES.get(timeframe, _TIMEFRAMES["H1"])
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            log.error("No rates for %s: %s", symbol, mt5.last_error())
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        return df[["open", "high", "low", "close", "tick_volume"]]

    def open_position_tickets(self) -> set[int]:
        """Tickets of all currently-open positions. Empty set in stub mode."""
        if not MT5_AVAILABLE or not self._connected:
            return set()
        positions = mt5.positions_get()
        if positions is None:
            return set()
        return {p.ticket for p in positions}

    def open_positions_by_magic(self, magic: int) -> list[dict]:
        """Details of currently-open positions for a magic — used to re-attach
        them to the monitor after a restart (so their close still alerts/trails)."""
        if not MT5_AVAILABLE or not self._connected:
            return []
        from datetime import datetime, timezone

        positions = mt5.positions_get()
        if not positions:
            return []
        out: list[dict] = []
        for p in positions:
            if getattr(p, "magic", 0) != magic:
                continue
            out.append({
                "ticket": int(p.ticket),
                "symbol": p.symbol,
                "direction": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                "entry": float(p.price_open),
                "sl": float(p.sl),
                "tp": float(p.tp),
                "lots": float(p.volume),
                "opened_at": mt5_ts_to_utc(p.time),
                "strategy": strategy_from_comment(getattr(p, "comment", "")),
            })
        return out

    def fetch_close_result(self, ticket: int) -> dict | None:
        """For a ticket no longer open, find the closing deal and return its fill
        price and realised profit. Returns None if not yet resolvable (try again
        next poll)."""
        if not MT5_AVAILABLE or not self._connected:
            return None
        deals = mt5.history_deals_get(position=ticket)
        if not deals:
            return None
        # The exit deal is the last OUT deal (the close); its reason says WHY it
        # closed (SL / TP / manual) — not whether a stop was trailed.
        outs = [d for d in deals if getattr(d, "entry", None) == mt5.DEAL_ENTRY_OUT]
        closing = outs[-1] if outs else deals[-1]
        pnl = sum(d.profit + getattr(d, "commission", 0.0) + getattr(d, "swap", 0.0)
                  for d in deals)
        return {
            "price": float(closing.price),
            "pnl": float(pnl),
            "reason": _deal_reason_str(closing.reason),
        }

    def closed_trades_by_magic(self, magic: int, days: int = 7) -> list[dict]:
        """All CLOSED positions for a magic number from MT5 deal history — the
        source of truth that survives restarts. Used to reconcile the History
        store so no trade is ever missed."""
        if not MT5_AVAILABLE or not self._connected:
            return []
        from datetime import datetime, timedelta, timezone

        # MT5 stamps deal.time in BROKER-SERVER time, which can run hours ahead of
        # the local clock. Building `to` from local now() therefore clips trades
        # that just closed (their server timestamp sits "in the future"), so they
        # never get reconciled into History. Use a wide upper bound — there are no
        # real deals in the future, so over-shooting is safe.
        frm = datetime.now() - timedelta(days=days + 1)
        to = datetime.now() + timedelta(days=1)
        deals = mt5.history_deals_get(frm, to)
        if not deals:
            return []

        by_pos: dict[int, list] = {}
        for d in deals:
            if getattr(d, "magic", 0) != magic:
                continue
            by_pos.setdefault(d.position_id, []).append(d)

        out: list[dict] = []
        for pid, ds in by_pos.items():
            ds = sorted(ds, key=lambda x: x.time)
            ins = [d for d in ds if getattr(d, "entry", None) == mt5.DEAL_ENTRY_IN]
            outs = [d for d in ds if getattr(d, "entry", None) == mt5.DEAL_ENTRY_OUT]
            if not ins or not outs:
                continue  # position still open (no exit deal yet)
            entry, exit_ = ins[0], outs[-1]
            pnl = sum(d.profit + getattr(d, "commission", 0.0) + getattr(d, "swap", 0.0)
                      for d in ds)
            out.append({
                "position_id": int(pid),
                "symbol": entry.symbol,
                "direction": "BUY" if entry.type == mt5.DEAL_TYPE_BUY else "SELL",
                "entry_price": float(entry.price),
                "close_price": float(exit_.price),
                "lots": float(entry.volume),
                "pnl": round(pnl, 2),
                "reason": _deal_reason_str(exit_.reason),
                "opened_at": mt5_ts_to_utc(entry.time),
                "closed_at": mt5_ts_to_utc(exit_.time),
                "strategy": strategy_from_comment(getattr(entry, "comment", "")),
            })
        return out

    def symbol_spec(self, asset: str) -> dict | None:
        """Trade specs needed to build a valid order: point, digits, min stop
        distance, spread, min volume, and current bid/ask. None in stub mode."""
        if not MT5_AVAILABLE or not self._connected:
            return None
        symbol = to_terminal_symbol(asset)
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        if not info.visible:
            mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return {
            "symbol": symbol,
            "point": info.point,
            "digits": info.digits,
            "stops_level": info.trade_stops_level,
            "spread": info.spread,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "trade_tick_value": info.trade_tick_value,
            "trade_tick_size": info.trade_tick_size,
            "ask": tick.ask,
            "bid": tick.bid,
        }

    def volume_for_risk(self, asset: str, entry: float, stop_loss: float,
                        risk_money: float) -> dict | None:
        """Return a broker-valid volume sized from the stop distance.

        The result is rounded DOWN to the broker's volume step. If the broker's
        minimum volume would exceed the requested risk, the trade is rejected by
        returning ``None`` rather than silently taking too much risk.
        """
        spec = self.symbol_spec(asset)
        if spec is None or risk_money <= 0 or entry == stop_loss:
            return None
        tick_size = float(spec.get("trade_tick_size") or 0.0)
        tick_value = float(spec.get("trade_tick_value") or 0.0)
        step = float(spec.get("volume_step") or 0.0)
        minimum = float(spec.get("volume_min") or 0.0)
        maximum = float(spec.get("volume_max") or 0.0)
        if tick_size <= 0 or tick_value <= 0 or step <= 0 or minimum <= 0:
            log.warning("Incomplete MT5 risk specs for %s: %s", asset, spec)
            return None

        risk_per_lot = abs(float(entry) - float(stop_loss)) / tick_size * tick_value
        raw_lots = float(risk_money) / risk_per_lot
        if raw_lots < minimum:
            log.warning("Skipping %s: minimum %.4f lots risks %.2f > budget %.2f.",
                        asset, minimum, risk_per_lot * minimum, risk_money)
            return None

        lots = math.floor(raw_lots / step + 1e-9) * step
        if maximum > 0:
            lots = min(lots, maximum)
        lots = round(lots, max(0, int(round(-math.log10(step)))))
        if lots < minimum:
            return None
        return {
            "lots": lots,
            "risk_per_lot": risk_per_lot,
            "risk_money": risk_per_lot * lots,
            "raw_lots": raw_lots,
            "volume_min": minimum,
            "volume_max": maximum,
            "volume_step": step,
        }

    def calc_margin(self, asset: str, direction: str, lots: float, price: float) -> float | None:
        """Margin (capital deployed) for the prospective order, per the broker."""
        if not MT5_AVAILABLE or not self._connected:
            return None
        symbol = to_terminal_symbol(asset)
        order_type = mt5.ORDER_TYPE_BUY if direction.upper() == "BUY" else mt5.ORDER_TYPE_SELL
        return mt5.order_calc_margin(order_type, symbol, lots, price)

    def place_order(self, asset: str, direction: str, lots: float,
                    sl: float, tp: float, strategy: str | None = None) -> dict:
        """Send a market order to MT5. Returns
        {ok, ticket, price, retcode, reason}. Never raises.

        `strategy` is stamped into the order comment ("IT <name>") so trades
        that outlive a backend restart — or close while it's down — can be
        re-attributed from MT5 instead of landing in History as strategy=None."""
        symbol = to_terminal_symbol(asset)
        log.info("ORDER %s %s %.2f lots sl=%s tp=%s", direction, symbol, lots, sl, tp)
        if not MT5_AVAILABLE or not self._connected:
            return {"ok": False, "ticket": None, "reason": "MT5 not connected (stub mode)"}

        # Make sure the symbol is visible in Market Watch before trading it.
        info = mt5.symbol_info(symbol)
        if info is None:
            return {"ok": False, "ticket": None, "reason": f"Unknown symbol '{symbol}'"}
        if not info.visible and not mt5.symbol_select(symbol, True):
            return {"ok": False, "ticket": None, "reason": f"Could not select '{symbol}'"}

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"ok": False, "ticket": None, "reason": f"No tick for '{symbol}'"}

        is_buy = direction.upper() == "BUY"
        order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
        price = tick.ask if is_buy else tick.bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lots),
            "type": order_type,
            "price": price,
            "sl": float(sl),
            "tp": float(tp),
            "deviation": 20,                 # max slippage in points
            "magic": _MAGIC,
            "comment": (f"IT {strategy}"[:31] if strategy else "IntelliTrade"),
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(info),
        }

        result = mt5.order_send(request)
        if result is None:
            return {"ok": False, "ticket": None,
                    "reason": f"order_send returned None: {mt5.last_error()}"}
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {"ok": False, "ticket": None, "retcode": result.retcode,
                    "reason": f"retcode {result.retcode}: {result.comment}"}
        return {"ok": True, "ticket": result.order, "price": result.price,
                "retcode": result.retcode, "reason": "filled"}

    def modify_position(self, ticket: int, sl: float | None = None,
                        tp: float | None = None) -> dict:
        """Move the SL/TP of an OPEN position (MT5 TRADE_ACTION_SLTP). Used by the
        trailing-stop manager — only ever tightens risk, never opens a trade, so
        it needs no live-money guard. Clamps SL/TP to the broker's min stop
        distance from the current price. Returns {ok, retcode, reason}."""
        if not MT5_AVAILABLE or not self._connected:
            return {"ok": False, "reason": "MT5 not connected (stub mode)"}
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return {"ok": False, "reason": f"position {ticket} not open"}
        pos = positions[0]
        symbol = pos.symbol
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if info is None or tick is None:
            return {"ok": False, "reason": f"no symbol/tick for '{symbol}'"}

        is_buy = pos.type == mt5.ORDER_TYPE_BUY
        point = info.point or 0.0
        min_dist = (info.trade_stops_level or 0) * point

        new_sl = float(sl) if sl is not None else pos.sl
        new_tp = float(tp) if tp is not None else pos.tp
        # Clamp the SL to a valid distance from the side it would close on.
        if new_sl:
            if is_buy:
                new_sl = min(new_sl, tick.bid - min_dist)
            else:
                new_sl = max(new_sl, tick.ask + min_dist)
            new_sl = round(new_sl, info.digits)

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": int(ticket),
            "sl": new_sl,
            "tp": round(new_tp, info.digits) if new_tp else 0.0,
            "magic": _MAGIC,
        }
        result = mt5.order_send(request)
        if result is None:
            return {"ok": False, "reason": f"order_send None: {mt5.last_error()}"}
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {"ok": False, "retcode": result.retcode,
                    "reason": f"retcode {result.retcode}: {result.comment}"}
        return {"ok": True, "sl": new_sl, "tp": new_tp, "retcode": result.retcode}

    def open_gold_tickets(self) -> list[int]:
        """Tickets of OPEN IntelliTrade gold positions (Friday-cutoff helper)."""
        if not MT5_AVAILABLE or not self._connected:
            return []
        return [p.ticket for p in (mt5.positions_get() or [])
                if p.magic == _MAGIC and "XAU" in p.symbol.upper()]

    def close_position(self, ticket: int) -> dict:
        """Market-close an OPEN position with an opposite deal. Used by the
        Friday gold cutoff. Returns {ok, price, reason}. Never raises."""
        if not MT5_AVAILABLE or not self._connected:
            return {"ok": False, "reason": "MT5 not connected (stub mode)"}
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return {"ok": False, "reason": f"position {ticket} not open"}
        pos = positions[0]
        info = mt5.symbol_info(pos.symbol)
        tick = mt5.symbol_info_tick(pos.symbol)
        if info is None or tick is None:
            return {"ok": False, "reason": f"no symbol/tick for '{pos.symbol}'"}
        closing_buy = pos.type != mt5.ORDER_TYPE_BUY   # close a SELL by buying back
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": mt5.ORDER_TYPE_BUY if closing_buy else mt5.ORDER_TYPE_SELL,
            "position": int(ticket),
            "price": tick.ask if closing_buy else tick.bid,
            "deviation": 20,
            "magic": _MAGIC,
            "comment": "IntelliTrade Fri gold close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(info),
        }
        result = mt5.order_send(request)
        if result is None:
            return {"ok": False, "reason": f"order_send returned None: {mt5.last_error()}"}
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {"ok": False, "retcode": result.retcode,
                    "reason": f"retcode {result.retcode}: {result.comment}"}
        return {"ok": True, "price": result.price, "reason": "closed"}

    @staticmethod
    def _filling_mode(info) -> int:
        """Pick a filling mode the symbol actually supports (broker-dependent)."""
        flags = info.filling_mode
        if flags & getattr(mt5, "SYMBOL_FILLING_IOC", 2):
            return mt5.ORDER_FILLING_IOC
        if flags & getattr(mt5, "SYMBOL_FILLING_FOK", 1):
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN


def strategy_from_comment(comment: str) -> str | None:
    """Recover the strategy name from an 'IT <name>' order comment (None if
    the order predates comment-stamping or was tagged plain 'IntelliTrade')."""
    c = (comment or "").strip()
    if c.startswith("IT ") and len(c) > 3:
        return c[3:].strip() or None
    return None


mt5_client = MT5Client()
