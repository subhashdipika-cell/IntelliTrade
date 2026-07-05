"""Historical market-data source for backtesting.

Two sources:
  • "mt5"      → live pull from the terminal (mt5_client.fetch_ohlcv) — always current.
  • "imported" → IntelliTrade's OWN copy, consolidated once from AlphaEdge's
                 scheduled collector CSVs. Decoupled from AlphaEdge (survives even
                 if that app/folder changes) but can go stale until re-imported.

AlphaEdge stores per-snapshot CSVs (`{SYMBOL}_{TF}_{date}.csv`, MT5 schema:
time,open,high,low,close,tick_volume,spread,real_volume). The snapshots overlap
heavily, so the importer concatenates ALL of them (plus the `_spot_archive`
sub-folder) and DEDUPES by timestamp into one consolidated file per asset+TF at
`app/data/market/{ASSET}_{TF}.csv`.
"""
from __future__ import annotations

import glob
import os

import pandas as pd

from app.core.config import settings
from app.core.constants import SUPPORTED_ASSETS, to_terminal_symbol
from app.core.logging_setup import get_logger
from app.services.mt5_client import mt5_client

log = get_logger("services.market_data")

_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
_MARKET_DIR = os.path.join(_DATA_DIR, "market")
_COLS = ["open", "high", "low", "close", "tick_volume"]
_TIMEFRAMES = ("M1", "M5", "H1")


def _imported_path(asset: str, timeframe: str) -> str:
    return os.path.join(_MARKET_DIR, f"{asset.upper()}_{timeframe.upper()}.csv")


def import_from_alphaedge(assets: list[str] | None = None,
                          timeframes: list[str] | None = None) -> dict:
    """Consolidate AlphaEdge's collector CSVs into IntelliTrade's data dir.
    Returns a per-dataset summary. Re-run any time to refresh."""
    src = settings.alphaedge_data_dir
    assets = assets or list(SUPPORTED_ASSETS)
    timeframes = timeframes or list(_TIMEFRAMES)
    if not os.path.isdir(src):
        return {"ok": False, "error": f"AlphaEdge data dir not found: {src}"}

    os.makedirs(_MARKET_DIR, exist_ok=True)
    summary: dict[str, dict] = {}
    for asset in assets:
        prefix = to_terminal_symbol(asset)  # BTC→BTCUSD, GOLD→XAUUSD+
        for tf in timeframes:
            # Main folder + the archive sub-folder, all dated snapshots.
            patterns = [
                os.path.join(src, f"{prefix}_{tf}_*.csv"),
                os.path.join(src, "_spot_archive", f"{prefix}_{tf}_*.csv"),
            ]
            files = sorted({f for p in patterns for f in glob.glob(p)})
            key = f"{asset.upper()}_{tf.upper()}"
            if not files:
                summary[key] = {"rows": 0, "files": 0, "note": "no source files"}
                continue
            frames = []
            for f in files:
                try:
                    frames.append(pd.read_csv(f))
                except Exception as exc:  # noqa: BLE001 — skip a bad snapshot
                    log.warning("Skipping unreadable CSV %s: %s", f, exc)
            if not frames:
                summary[key] = {"rows": 0, "files": len(files), "note": "unreadable"}
                continue
            df = pd.concat(frames, ignore_index=True)
            df["time"] = pd.to_datetime(df["time"])
            df = (df.drop_duplicates(subset="time", keep="last")
                    .sort_values("time")
                    .reset_index(drop=True))
            df.to_csv(_imported_path(asset, tf), index=False)
            summary[key] = {
                "rows": len(df),
                "files": len(files),
                "first": str(df["time"].iloc[0]),
                "last": str(df["time"].iloc[-1]),
            }
            log.info("Imported %s: %d bars from %d files.", key, len(df), len(files))
    return {"ok": True, "source": src, "datasets": summary}


def available() -> dict:
    """What's been imported (for the UI), with row counts + date span."""
    out: dict[str, dict] = {}
    if not os.path.isdir(_MARKET_DIR):
        return out
    for asset in SUPPORTED_ASSETS:
        for tf in _TIMEFRAMES:
            path = _imported_path(asset, tf)
            if not os.path.exists(path):
                continue
            try:
                df = pd.read_csv(path, usecols=["time"])
                out[f"{asset}_{tf}"] = {
                    "rows": len(df),
                    "first": str(df["time"].iloc[0]) if len(df) else None,
                    "last": str(df["time"].iloc[-1]) if len(df) else None,
                }
            except Exception:  # noqa: BLE001
                continue
    return out


def load_imported(asset: str, timeframe: str, count: int = 3000) -> pd.DataFrame:
    """Read a consolidated file into the same shape as mt5_client.fetch_ohlcv."""
    path = _imported_path(asset, timeframe)
    if not os.path.exists(path):
        return pd.DataFrame(columns=_COLS)
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"])
    df = df.set_index("time").sort_index()
    cols = [c for c in _COLS if c in df.columns]
    return df[cols].tail(count)


def get_ohlcv(asset: str, timeframe: str, count: int, source: str = "mt5") -> pd.DataFrame:
    """Dispatch to the requested data source (backtest entry point)."""
    if source == "imported":
        return load_imported(asset, timeframe, count)
    return mt5_client.fetch_ohlcv(asset, timeframe, count)
