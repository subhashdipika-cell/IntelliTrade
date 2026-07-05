"""Central configuration, loaded from the root .env file."""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives at the repo root (one level above /backend)
ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_PATH, extra="ignore")

    # MT5 / Vantage — DEMO profile (the mt5_* fields are the demo account)
    mt5_terminal_path: str = ""
    mt5_login: int | None = None
    mt5_password: str = ""
    mt5_server: str = ""
    # LIVE / real-money profile (filled later; empty until you opt in).
    # Use a SEPARATE terminal install for live so it's isolated from the demo
    # terminal (which smart-money-trader shares). Falls back to the demo path if unset.
    mt5_live_terminal_path: str = ""
    mt5_live_login: int | None = None
    mt5_live_password: str = ""
    mt5_live_server: str = ""
    # Default active profile on startup. ALLOW_LIVE is the real-money kill switch:
    # live orders (and switching to live) are refused unless it is exactly true.
    mt5_account_type: str = "DEMO"  # DEMO | LIVE
    allow_live: bool = False

    # Obsidian
    obsidian_vault_path: str = ""
    obsidian_trades_dir: str = ""
    # Auto-log closed trades + weekly backtest snapshots into the vault (with a
    # market-regime tag) so they can be analysed/fine-tuned later.
    obsidian_autolog_enabled: bool = True

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_enabled: bool = True

    # LLM (OpenAI-compatible /chat/completions). Two providers, same protocol:
    #   "openrouter" → cloud (needs OPENAI_API_KEY)
    #   "ollama"     → local, free, no key (needs Ollama running on this machine).
    #                  Set LLM_MODEL to a pulled tag, e.g. llama3 / mistral / qwen2.5.
    # Primary model is tried first, fallback on error/rate-limit.
    llm_provider: str = "openrouter"
    openai_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ollama_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "openai/gpt-4o-mini"
    llm_model_fallback: str = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
    # Strategy Review uses its OWN provider/model — it needs ~500 tokens of JSON,
    # too slow on a local CPU model, so it defaults to OpenRouter even when the
    # gatekeeper runs on local Ollama. (Leave review_provider blank to follow the
    # global provider.)
    review_provider: str = "openrouter"
    review_model: str = "openai/gpt-4o-mini"

    # App
    base_currency: str = "USD"
    # External historical-data archive (AlphaEdge's scheduled collector). Its CSVs
    # are MT5-format and cover BTCUSD/ETHUSD/XAUUSD+, so they can be imported into
    # IntelliTrade's own data dir for offline / intraday backtesting.
    alphaedge_data_dir: str = r"D:\alphaedge\strategy-lab\data"
    app_name: str = "IntelliTrade"  # stamped on every Telegram alert so this
                                    # app's alerts are distinct from the other
                                    # MT5 bots on this machine (magic 770011)

    @field_validator("mt5_login", "mt5_live_login", mode="before")
    @classmethod
    def _empty_login_to_none(cls, v):
        # an unset "MT5_LIVE_LOGIN=" in .env arrives as "" — treat as None.
        return None if v in ("", None) else v

    @property
    def has_live(self) -> bool:
        """True once the live/real-money profile is fully configured."""
        return bool(self.mt5_live_login and self.mt5_live_password and self.mt5_live_server)

    def credentials_for(self, account_type: str) -> tuple[int | None, str, str]:
        """(login, password, server) for the requested profile."""
        if account_type.upper() == "LIVE":
            return self.mt5_live_login, self.mt5_live_password, self.mt5_live_server
        return self.mt5_login, self.mt5_password, self.mt5_server

    def terminal_path_for(self, account_type: str) -> str:
        """Terminal executable for the profile. LIVE uses its own install when
        set, so it's isolated from the demo terminal."""
        if account_type.upper() == "LIVE" and self.mt5_live_terminal_path:
            return self.mt5_live_terminal_path
        return self.mt5_terminal_path

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def obsidian_backtests_dir(self) -> str:
        """Sibling of the trades folder for backtest snapshots (…/raw/backtests)."""
        if not self.obsidian_trades_dir:
            return ""
        import os
        return os.path.join(os.path.dirname(self.obsidian_trades_dir.rstrip("/\\")), "backtests")

    @property
    def llm_is_local(self) -> bool:
        return self.llm_provider.lower() == "ollama"

    @property
    def llm_base_url(self) -> str:
        """Active provider's OpenAI-compatible base URL."""
        return self.ollama_base_url if self.llm_is_local else self.openrouter_base_url

    def llm_endpoint(self, provider: str | None = None) -> tuple[str, str, bool]:
        """(base_url, api_key, is_local) for a provider — defaults to the global
        one. Lets a single feature (e.g. Strategy Review) override the provider."""
        p = (provider or self.llm_provider).lower()
        if p == "ollama":
            return self.ollama_base_url, (self.openai_api_key or "ollama"), True
        return self.openrouter_base_url, self.openai_api_key, False

    @property
    def llm_configured(self) -> bool:
        # Local Ollama needs no API key; cloud providers do.
        return self.llm_is_local or bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
