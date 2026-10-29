"""Cloudflare Workers AI client with cache, replay and deterministic fallback.

Rules from the blueprint:
  * LLM output is parsed as JSON and validated by schema + guardrails.
  * It is never executed, never used in a query, and never forwarded to another
    agent's prompt (only numeric fields cross agents).
  * Every call is cached; `LLM_MODE=replay` serves real recorded outputs, which
    is disclosed in the README and the UI.
"""
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
import structlog

from app.settings import settings

logger = structlog.get_logger()

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LLMUnavailable(Exception):
    """Raised when no live call is possible and nothing is cached."""


def extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    cleaned = _FENCE.sub("", text).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class LLMClient:
    def __init__(self, db=None):
        self.db = db
        self.mode = settings.LLM_MODE
        self.provider = "cloudflare"
        self.model = settings.CF_MODEL

    def _cache_key(self, purpose: str, system: str, user: str) -> str:
        blob = f"{self.provider}|{self.model}|{purpose}|{system}|{user}"
        return hashlib.sha256(blob.encode()).hexdigest()

    async def _cache_get(self, key: str) -> Optional[str]:
        if self.db is not None:
            doc = await self.db.llm_cache.find_one({"key_hash": key})
            if doc:
                return doc.get("response_text")
        path = settings.LLM_CACHE_PATH
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                return data.get(key)
            except (OSError, json.JSONDecodeError):
                return None
        return None

    async def _cache_put(self, key: str, text: str) -> None:
        if self.db is not None:
            await self.db.llm_cache.update_one(
                {"key_hash": key},
                {"$set": {"response_text": text, "provider": self.provider,
                          "model": self.model,
                          "created_at": datetime.now(timezone.utc)}},
                upsert=True,
            )
        try:
            path = settings.LLM_CACHE_PATH
            data = {}
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            data[key] = text
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=1)
        except OSError as exc:  # read-only filesystem on some hosts
            logger.warning("llm_cache_file_skipped", error=str(exc))

    async def _call_live(self, system: str, user: str) -> str:
        if not (settings.CF_ACCOUNT_ID and settings.CF_API_TOKEN):
            raise LLMUnavailable("Cloudflare Workers AI credentials are not configured")
        url = (f"https://api.cloudflare.com/client/v4/accounts/"
               f"{settings.CF_ACCOUNT_ID}/ai/run/{settings.CF_MODEL}")
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": 400,
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {settings.CF_API_TOKEN}"}
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            raise LLMUnavailable(f"Workers AI returned {response.status_code}")
        body = response.json()
        if not body.get("success", True):
            raise LLMUnavailable("Workers AI reported failure")
        result = body.get("result") or {}
        text = result.get("response") if isinstance(result, dict) else None
        if isinstance(text, dict):
            return json.dumps(text)
        if not isinstance(text, str) or not text.strip():
            raise LLMUnavailable("empty Workers AI response")
        return text

    async def complete_json(self, purpose: str, system: str, user: str) -> Dict[str, Any]:
        """Return a validated dict plus provenance metadata."""
        key = self._cache_key(purpose, system, user)
        cached = await self._cache_get(key)

        if self.mode == "off":
            raise LLMUnavailable("LLM disabled (LLM_MODE=off)")
        if self.mode == "replay":
            if cached:
                parsed = extract_json(cached)
                if parsed:
                    return {"data": parsed, "source": "replay", "provider": self.provider, "model": self.model, "latency_ms": 0}
            raise LLMUnavailable("no cached LLM response for replay")

        started = time.perf_counter()
        try:
            text = await self._call_live(system, user)
            latency = int((time.perf_counter() - started) * 1000)
            parsed = extract_json(text)
            if not parsed:
                raise LLMUnavailable("model returned non-JSON")
            await self._cache_put(key, text)
            return {"data": parsed, "source": "live", "provider": self.provider,
                    "model": self.model, "latency_ms": latency}
        except Exception as exc:  # network, quota, parse
            logger.warning("llm_live_failed", purpose=purpose, error=str(exc))
            if cached:
                parsed = extract_json(cached)
                if parsed:
                    return {"data": parsed, "source": "cache", "provider": self.provider,
                            "model": self.model, "latency_ms": 0}
            raise LLMUnavailable(str(exc))


def get_llm(db=None) -> LLMClient:
    return LLMClient(db)
