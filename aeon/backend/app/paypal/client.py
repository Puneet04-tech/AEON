"""PayPal REST client (sandbox).

Two modes:
  * sandbox: real calls to api-m.sandbox.paypal.com with OAuth2 client credentials
  * mock:    a clearly-labelled simulated adapter used only when credentials are
             absent (or PAYPAL_MODE=mock). It never contacts PayPal.

Live PayPal is refused by settings validation: AEON is sandbox-only.
"""
import asyncio
import time
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

import httpx
import structlog

from app.settings import settings

logger = structlog.get_logger()


class PayPalError(Exception):
    def __init__(self, message: str, status: int = 502, code: str = "paypal_error", details: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details


def micro_to_decimal(amount_micro: int) -> str:
    """micro-USD -> a PayPal amount string with exactly two decimals."""
    value = (Decimal(amount_micro) / Decimal(1_000_000)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{value:.2f}"


def to_micro(amount: str) -> int:
    return int((Decimal(str(amount)) * Decimal(1_000_000)).to_integral_value(rounding=ROUND_HALF_UP))


class PayPalClient:
    def __init__(self, db=None, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.db = db
        self.mode = settings.paypal_effective_mode
        self.base_url = settings.paypal_base_url
        self.transport = transport
        self._token: Optional[str] = None
        self._token_expires: float = 0.0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ auth
    async def _access_token(self) -> str:
        if self.mode == "mock":
            return "mock-token"
        now = time.time()
        if self._token and now < self._token_expires - 60:
            return self._token
        async with self._lock:
            if self._token and time.time() < self._token_expires - 60:
                return self._token
            async with httpx.AsyncClient(timeout=20.0, transport=self.transport) as client:
                response = await client.post(
                    f"{self.base_url}/v1/oauth2/token",
                    data={"grant_type": "client_credentials"},
                    auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
                    headers={"Accept": "application/json"},
                )
            if response.status_code != 200:
                raise PayPalError("could not obtain PayPal access token",
                                  code="auth_failed", details=response.text[:300])
            body = response.json()
            self._token = body["access_token"]
            self._token_expires = time.time() + int(body.get("expires_in", 300))
            return self._token

    async def request(self, method: str, path: str, json: Optional[dict] = None,
                      headers: Optional[dict] = None) -> dict:
        token = await self._access_token()
        request_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        request_headers.update(headers or {})
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=30.0, transport=self.transport) as client:
                response = await client.request(method, url, json=json, headers=request_headers)
        except httpx.HTTPError as exc:
            raise PayPalError(f"network error talking to PayPal: {exc}", code="network")
        if response.status_code >= 400:
            raise PayPalError(f"PayPal returned {response.status_code} for {method} {path}",
                              status=502, code="http_error", details=response.text[:500])
        if not response.content:
            return {}
        return response.json()

    # ------------------------------------------------------------------ mock
    async def _mock_store(self, key: str, doc: dict) -> None:
        if self.db is not None:
            await self.db.kv.update_one({"key": key}, {"$set": {"value": doc}}, upsert=True)

    async def _mock_get(self, key: str) -> Optional[dict]:
        if self.db is None:
            return None
        doc = await self.db.kv.find_one({"key": key})
        return doc.get("value") if doc else None

    def mock_id(self, prefix: str) -> str:
        return f"MOCK-{prefix}-{uuid.uuid4().hex[:12].upper()}"

    @property
    def is_mock(self) -> bool:
        return self.mode == "mock"
