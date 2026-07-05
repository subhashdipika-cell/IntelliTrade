"""Internal asset names <-> Vantage MT5 terminal symbols."""

# Internal key -> Vantage MT5 execution symbol.
# Gold carries the "+" suffix on Vantage raw/spread accounts.
SYMBOL_MAPPER: dict[str, str] = {
    "BTC": "BTCUSD",
    "ETH": "ETHUSD",
    "GOLD": "XAUUSD+",
}

# Internal key -> TradingView widget symbol (for the frontend charts).
TRADINGVIEW_MAPPER: dict[str, str] = {
    "BTC": "BINANCE:BTCUSDT",
    "ETH": "BINANCE:ETHUSDT",
    "GOLD": "OANDA:XAUUSD",
}

SUPPORTED_ASSETS = tuple(SYMBOL_MAPPER.keys())

# Units of the base instrument in ONE standard lot, per Vantage contract specs.
#   XAUUSD: 1 lot = 100 troy ounces
#   BTCUSD / ETHUSD: 1 lot = 1 coin
# Backtest position size is tracked in base units, so lots = units / contract_size.
CONTRACT_SIZES: dict[str, float] = {
    "BTC": 1.0,
    "ETH": 1.0,
    "GOLD": 100.0,
}

# Commission per LOT per SIDE (account currency). These are REFERENCE defaults —
# replace with the exact figures from your Vantage account statement. Crypto on
# many Vantage account types is spread-only (0 commission).
DEFAULT_COMMISSION_PER_LOT: dict[str, float] = {
    "BTC": 0.0,
    "ETH": 0.0,
    "GOLD": 3.0,
}


def to_terminal_symbol(asset_key: str) -> str:
    """'GOLD' -> 'XAUUSD+'. Falls back to the input if unknown."""
    return SYMBOL_MAPPER.get(asset_key.upper(), asset_key)


def contract_size(asset_key: str) -> float:
    """Base units per standard lot. Defaults to 1.0 for unknown assets."""
    return CONTRACT_SIZES.get(asset_key.upper(), 1.0)


def units_to_lots(asset_key: str, units: float) -> float:
    """Convert a backtest position size (base units) into standard lots."""
    return units / contract_size(asset_key)


def default_commission_per_lot(asset_key: str) -> float:
    return DEFAULT_COMMISSION_PER_LOT.get(asset_key.upper(), 0.0)
