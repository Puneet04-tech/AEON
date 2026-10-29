from pydantic_settings import BaseSettings
from typing import List, Optional
import os


class Settings(BaseSettings):
    # MongoDB
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    MONGODB_DB: str = os.getenv("MONGODB_DB", "aeon")
    
    # PayPal
    PAYPAL_CLIENT_ID: str = os.getenv("PAYPAL_CLIENT_ID", "")
    PAYPAL_CLIENT_SECRET: str = os.getenv("PAYPAL_CLIENT_SECRET", "")
    PAYPAL_WEBHOOK_ID: str = os.getenv("PAYPAL_WEBHOOK_ID", "")
    PAYPAL_ENV: str = os.getenv("PAYPAL_ENV", "sandbox")
    
    # Treasury & Limits (micro-USD)
    TREASURY_RESERVE_MICRO: int = int(os.getenv("TREASURY_RESERVE_MICRO", "10000000000"))
    PAYOUT_MIN_MICRO: int = int(os.getenv("PAYOUT_MIN_MICRO", "10000"))
    PAYOUT_DAILY_CAP_MICRO: int = int(os.getenv("PAYOUT_DAILY_CAP_MICRO", "1000000000"))
    APPROVAL_THRESHOLD_MICRO: int = int(os.getenv("APPROVAL_THRESHOLD_MICRO", "25000000"))
    
    # LLM
    CF_ACCOUNT_ID: str = os.getenv("CF_ACCOUNT_ID", "")
    CF_API_TOKEN: str = os.getenv("CF_API_TOKEN", "")
    CF_MODEL: str = os.getenv("CF_MODEL", "@cf/meta/llama-3.1-8b-instruct")
    LLM_PROVIDERS: str = os.getenv("LLM_PROVIDERS", "cloudflare")
    LLM_MODE: str = os.getenv("LLM_MODE", "live")
    
    # Security
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "change_me_in_production")
    HMAC_SHARED_SECRET: str = os.getenv("HMAC_SHARED_SECRET", "change_me_in_production")
    OPERATOR_PASSWORD_HASH: str = os.getenv("OPERATOR_PASSWORD_HASH", "")
    
    # Workers
    WORKER_URLS: str = os.getenv("WORKER_URLS", "http://localhost:8001,http://localhost:8002")
    
    # API
    ALLOWED_ORIGIN: str = os.getenv("ALLOWED_ORIGIN", "http://localhost:5173")
    RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
    RATE_LIMIT_MAX: int = int(os.getenv("RATE_LIMIT_MAX", "100"))
    JUDGE_SESSION_MINUTES: int = int(os.getenv("JUDGE_SESSION_MINUTES", "30"))
    JUDGE_SCENARIO_QUOTA: int = int(os.getenv("JUDGE_SCENARIO_QUOTA", "10"))
    
    @property
    def worker_urls_list(self) -> List[str]:
        return [url.strip() for url in self.WORKER_URLS.split(",")]
    
    @property
    def paypal_base_url(self) -> str:
        if self.PAYPAL_ENV == "live":
            return "https://api-m.paypal.com"
        return "https://api-m.sandbox.paypal.com"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
