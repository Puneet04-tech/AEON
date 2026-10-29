"""Worker signing, replay protection, metering and job limits."""
import hashlib
import hmac
import json
import sys
import time
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

WORKER = Path(__file__).resolve().parents[1]
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))

from app.main import app, state  # noqa: E402
from app.settings import settings  # noqa: E402


def signed_headers(method: str, path: str, body: bytes, ts: int = None, nonce: str = None,
                   secret: str = None, signature: str = None):
    ts = ts or int(time.time())
    nonce = nonce or uuid.uuid4().hex
    if signature is None:
        digest = hashlib.sha256(body).hexdigest()
        message = "\n".join([method.upper(), path, str(ts), nonce, digest]).encode()
        signature = hmac.new((secret or settings.hmac_secret).encode(), message,
                             hashlib.sha256).hexdigest()
    return {"X-AEON-Timestamp": str(ts), "X-AEON-Nonce": nonce, "X-AEON-Signature": signature}


@pytest.fixture(autouse=True)
def fresh_state():
    state["healthy"] = True
    yield
    state["healthy"] = True


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://worker") as http:
        yield http


async def post_job(client, job, headers=None):
    body = json.dumps(job, sort_keys=True, separators=(",", ":")).encode()
    return await client.post("/jobs", content=body,
                             headers=headers or signed_headers("POST", "/jobs", body))


async def test_health_is_public(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["healthy"] is True


async def test_job_requires_signature(client):
    body = json.dumps({"type": "matrix_multiply", "params": {"n": 16}}).encode()
    response = await client.post("/jobs", content=body)
    assert response.status_code == 401
    assert "signature rejected" in response.text


async def test_bad_signature_is_rejected(client):
    body = json.dumps({"type": "matrix_multiply", "params": {"n": 16}}).encode()
    headers = signed_headers("POST", "/jobs", body, secret="wrong-secret")
    response = await client.post("/jobs", content=body, headers=headers)
    assert response.status_code == 401


async def test_stale_timestamp_is_rejected(client):
    body = json.dumps({"type": "matrix_multiply", "params": {"n": 16}}).encode()
    headers = signed_headers("POST", "/jobs", body, ts=int(time.time()) - 3600)
    response = await client.post("/jobs", content=body, headers=headers)
    assert response.status_code == 401
    assert "stale_timestamp" in response.text


async def test_nonce_replay_is_rejected(client):
    body = json.dumps({"type": "matrix_multiply", "params": {"n": 16}}).encode()
    headers = signed_headers("POST", "/jobs", body)
    first = await client.post("/jobs", content=body, headers=headers)
    assert first.status_code == 200
    second = await client.post("/jobs", content=body, headers=headers)
    assert second.status_code == 401
    assert "replay" in second.text


async def test_matrix_job_returns_valid_checksum(client):
    from app.jobs import canonical_digest

    response = await post_job(client, {"job_id": "job1", "type": "matrix_multiply",
                                       "size": 32, "params": {"n": 32}})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["checksum"] == canonical_digest(body["result"])
    assert body["cpu_seconds"] >= 0
    assert body["result"]["n"] == 32


async def test_image_job_does_real_work(client):
    from app.jobs import canonical_digest

    response = await post_job(client, {"job_id": "job2", "type": "image_resize",
                                       "size": 307200, "params": {"width": 320, "height": 240}})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result"]["output"]["width"] == 320
    assert body["result"]["output"]["bytes"] > 0
    assert body["checksum"] == canonical_digest(body["result"])


async def test_matrix_size_limit(client):
    response = await post_job(client, {"type": "matrix_multiply", "params": {"n": 5000}})
    assert response.status_code == 422
    assert "size_limit" in response.text


async def test_unknown_job_type(client):
    response = await post_job(client, {"type": "gpu_training", "params": {}})
    assert response.status_code == 422


async def test_chaos_switch_blocks_jobs(client):
    body = json.dumps({"fail": True}, sort_keys=True, separators=(",", ":")).encode()
    response = await client.post("/admin/chaos", content=body,
                                 headers=signed_headers("POST", "/admin/chaos", body))
    assert response.status_code == 200
    assert response.json()["healthy"] is False

    health = await client.get("/health")
    assert health.json()["healthy"] is False

    job = await post_job(client, {"type": "matrix_multiply", "params": {"n": 8}})
    assert job.status_code == 503


async def test_chaos_requires_signature(client):
    response = await client.post("/admin/chaos", content=b'{"fail": true}')
    assert response.status_code == 401
