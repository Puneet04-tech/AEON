"""PayPal REST client (sandbox).

PayPal mode:
  * sandbox: real calls to api-m.sandbox.paypal.com with OAuth2 client credentials

When credentials are absent, PayPal actions fail explicitly as unavailable. AEON
does not simulate money movement.

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


def micro_to_decimal(amount_micro: int, currency: str = "USD") -> str:
    """micro-USD -> the amount string PayPal expects, in the order's currency.

    AEON keeps every balance in micro-USD. PayPal wants a bare decimal with no
    currency symbol, expressed in the order's own currency, so when the order
    currency is INR the value is converted at PAYPAL_USD_TO_INR (a $5.00 top-up
    becomes 415.00 INR).
    """
    value = Decimal(amount_micro) / Decimal(1_000_000)
    if currency.upper() == "INR":
        value = value * Decimal(str(settings.PAYPAL_USD_TO_INR))
    value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{value:.2f}"


def to_micro(amount: str, currency: str = "USD") -> int:
    """PayPal amount string -> micro-USD, reversing the currency conversion."""
    value = Decimal(str(amount).replace("₹", "").replace("$", "").strip())
    if currency.upper() == "INR":
        value = value / Decimal(str(settings.PAYPAL_USD_TO_INR))
    return int((value * Decimal(1_000_000)).to_integral_value(rounding=ROUND_HALF_UP))


class PayPalClient:
    def __init__(self, db=None, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.db = db
        self.mode = settings.paypal_effective_mode
        self.base_url = settings.paypal_base_url
        self.transport = transport
        self._token: Optional[str] = None
        self._token_expires: float = 0.0
        self._lock = asyncio.Lock()
        if self.mode == "unconfigured":
            raise PayPalError(
                "PayPal sandbox credentials are not configured",
                status=503,
                code="paypal_not_configured",
            )

    # ------------------------------------------------------------------ auth
    async def _access_token(self) -> str:
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
            # Surface PayPal's own error name (e.g. PAYOUT_NOT_AVAILABLE,
            # ORDER_NOT_APPROVED) so operators see the real cause instead of a
            # generic upstream failure.
            name, detail = "http_error", ""
            try:
                body = response.json()
                name = body.get("name") or name
                detail = body.get("message") or body.get("error_description") or ""
                issues = [d.get("issue") for d in (body.get("details") or []) if d.get("issue")]
                if issues:
                    name = issues[0]
                    detail = detail or ""
            except ValueError:
                detail = response.text[:300]
            message = f"PayPal {response.status_code} {name} for {method} {path}"
            if detail:
                message += f": {detail}"
            raise PayPalError(message, status=502, code=name, details=response.text[:500])
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
