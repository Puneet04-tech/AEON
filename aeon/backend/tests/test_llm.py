"""LLM client: JSON extraction, replay, off mode and live fallback."""
import json

import pytest

from app.llm.llm_client import LLMClient, LLMUnavailable, extract_json
from app.settings import settings


def test_extract_json_handles_fences_and_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure: {"price_micro": 500, "accept": false} done') == {
        "price_micro": 500, "accept": False}
    assert extract_json("no json here") is None
    assert extract_json('{"broken": ') is None
    assert extract_json("[1,2,3]") is None  # arrays are not accepted


async def test_off_mode_raises(db, monkeypatch):
    monkeypatch.setattr(settings, "LLM_MODE", "off")
    with pytest.raises(LLMUnavailable):
        await LLMClient(db).complete_json("p", "s", "u")


async def test_replay_mode_serves_cached_real_output(db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "LLM_MODE", "replay")
    monkeypatch.setattr(settings, "LLM_CACHE_PATH", str(tmp_path / "cache.json"))
    client = LLMClient(db)
    key = client._cache_key("buyer_offer", "sys", "user")
    await client._cache_put(key, '{"price_micro": 42000, "accept": false, "reasoning": "banded"}')

    result = await LLMClient(db).complete_json("buyer_offer", "sys", "user")
    assert result["source"] == "replay"
    assert result["data"]["price_micro"] == 42000


async def test_replay_mode_without_cache_raises(db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "LLM_MODE", "replay")
    monkeypatch.setattr(settings, "LLM_CACHE_PATH", str(tmp_path / "empty.json"))
    with pytest.raises(LLMUnavailable):
        await LLMClient(db).complete_json("missing", "s", "u")


async def test_live_failure_falls_back_to_cache(db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "LLM_MODE", "live")
    monkeypatch.setattr(settings, "LLM_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setattr(settings, "CF_ACCOUNT_ID", "")
    monkeypatch.setattr(settings, "CF_API_TOKEN", "")
    client = LLMClient(db)
    key = client._cache_key("seller_offer", "sys", "user")
    await client._cache_put(key, '{"price_micro": 51000, "accept": true}')

    result = await client.complete_json("seller_offer", "sys", "user")
    assert result["source"] == "cache"
    assert result["data"]["accept"] is True


async def test_live_without_cache_raises(db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "LLM_MODE", "live")
    monkeypatch.setattr(settings, "LLM_CACHE_PATH", str(tmp_path / "none.json"))
    monkeypatch.setattr(settings, "CF_ACCOUNT_ID", "")
    monkeypatch.setattr(settings, "CF_API_TOKEN", "")
    with pytest.raises(LLMUnavailable):
        await LLMClient(db).complete_json("uncached", "s", "u")


async def test_cache_roundtrip_survives_restart(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "LLM_CACHE_PATH", str(tmp_path / "cache.json"))
    client = LLMClient(db)
    await client._cache_put("abc", json.dumps({"price_micro": 1}))
    fresh = LLMClient(db)
    assert await fresh._cache_get("abc") == json.dumps({"price_micro": 1})
