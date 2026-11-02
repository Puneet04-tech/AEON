"""Environment configuration for the AEON API.

Every secret is read from the environment. Nothing here is ever committed.
Money is integer micro-USD (1 USD = 1,000,000) everywhere.
"""
from functools import lru_cache
from typing import List, Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8",
                                      extra="ignore", case_sensitive=True)

    # Service
    APP_ENV: Literal["dev", "staging", "production"] = "dev"
    AUTO_SEED: bool = True
    APP_VERSION: str = "1.0.0"
    SERVICE_NAME: str = "aeon-api"
    LOG_LEVEL: str = "INFO"

    # MongoDB
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "aeon"

    # PayPal (sandbox only unless explicitly switched, which the code refuses)
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_WEBHOOK_ID: str = ""
    PAYPAL_ENV: Literal["sandbox", "live"] = "sandbox"
    PAYPAL_MODE: Literal["sandbox", "mock"] = "sandbox"
    PAYPAL_RETURN_URL: str = "http://localhost:5173/?funding=return"
    PAYPAL_CANCEL_URL: str = "http://localhost:5173/?funding=cancel"
    # The merchant profile here is country IN, which PayPal only allows to
    # receive USD (INR orders are rejected 422 CURRENCY_NOT_SUPPORTED). Keep the
    # order currency USD; the payer account must also be a USD-capable sandbox
    # account, otherwise checkout fails with "currency is not valid".
    PAYPAL_CURRENCY: str = "USD"
    # Only used when PAYPAL_CURRENCY is switched to a non-USD code. AEON books
    # everything in micro-USD, so amounts are converted at this rate out and back.
    PAYPAL_USD_TO_INR: float = 83.0
    ALLOW_MOCK_PAYPAL: bool = False
    PAYPAL_SENDER_BATCH_ID_PREFIX: str = "AEON"

    # Treasury / settlement limits, micro-USD
    TREASURY_RESERVE_MICRO: int = 20_000_000  # 20 USD kept unspent in the float
    PAYOUT_MIN_MICRO: int = 10_000
    PAYOUT_DAILY_CAP_MICRO: int = 1_000_000_000
    APPROVAL_THRESHOLD_MICRO: int = 25_000_000
    FUNDING_MAX_MICRO: int = 50_000_000
    MAX_TRADE_MICRO: int = 5_000_000

    # LLM (Cloudflare Workers AI)
    CF_ACCOUNT_ID: str = ""
    CF_API_TOKEN: str = ""
    CF_MODEL: str = "@cf/meta/llama-3.1-8b-instruct"
    LLM_PROVIDERS: str = "cloudflare"
    LLM_MODE: Literal["live", "replay", "off"] = "live"
    LLM_CACHE_PATH: str = ".llm_cache.json"
    LLM_TIMEOUT_SECONDS: float = 20.0

    # Secrets
    SESSION_SECRET: str = "dev-session-secret-change-me"
    HMAC_SHARED_SECRET: str = "dev-hmac-secret-change-me"
    OPERATOR_PASSWORD_HASH: str = ""
    OPERATOR_PASSWORD: str = ""  # dev-only fallback, never set in production

    # Workers
    WORKER_URLS: str = "http://localhost:8001,http://localhost:8002"
    WORKER_TIMEOUT_SECONDS: float = 15.0

    # Web / CORS
    ALLOWED_ORIGIN: str = "http://localhost:5173"
    DASHBOARD_DIR: str = "dashboard/dist"

    # Rate limiting
    RATE_LIMIT_WINDOW: int = 60
    RATE_LIMIT_MAX: int = 120

    # Judge mode
    JUDGE_SESSION_MINUTES: int = 30
    JUDGE_SCENARIO_QUOTA: int = 10

    # Forecasts (simulated pricing inputs)
    WEATHER_LAT: float = 37.7749
    WEATHER_LON: float = -122.4194
    WEATHER_CACHE_SECONDS: int = 900
    ENABLE_FORECASTS: bool = True

    @property
    def worker_urls(self) -> List[str]:
        return [u.strip().rstrip("/") for u in self.WORKER_URLS.split(",") if u.strip()]

    @property
    def paypal_base_url(self) -> str:
        return "https://api-m.sandbox.paypal.com"

    @property
    def paypal_enabled(self) -> bool:
        return bool(self.PAYPAL_CLIENT_ID and self.PAYPAL_CLIENT_SECRET)

    @property
    def paypal_effective_mode(self) -> str:
        """Return sandbox only when PayPal credentials are configured.

        The mock adapter is available only to the isolated test harness; it is
        disabled by default and cannot be enabled accidentally in deployment.
        """
        if self.PAYPAL_MODE == "mock" and self.ALLOW_MOCK_PAYPAL:
            return "mock"
        return "sandbox" if self.paypal_enabled else "unconfigured"

    @property
    def cors_origins(self) -> List[str]:
        origins = {self.ALLOWED_ORIGIN, "http://localhost:5173", "http://127.0.0.1:5173"}
        return [o for o in origins if o]

    def assert_production_safe(self) -> Optional[str]:
        """Return a warning string when dev-only settings are in use."""
        if self.APP_ENV != "production":
            return None
        if self.SESSION_SECRET.startswith("dev-") or self.HMAC_SHARED_SECRET.startswith("dev-"):
            raise RuntimeError("Refusing to run production with default secrets")
        if self.PAYPAL_ENV == "live":
            raise RuntimeError("AEON is sandbox-only; PAYPAL_ENV=live is not supported")
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
