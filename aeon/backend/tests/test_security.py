"""Security pass: rate limiting, body limits, quotas, revocation, injection."""
import pytest

from app.main import rate_limiter
from app.security.sessions import issue_session, revoke_session


@pytest.fixture(autouse=True)
def reset_limiter():
    rate_limiter.max_requests = 10_000
    rate_limiter.reset()
    yield
    rate_limiter.max_requests = 10_000
    rate_limiter.reset()


async def test_rate_limit_returns_429(client):
    rate_limiter.max_requests = 2
    rate_limiter.reset()
    codes = [(await client.get("/api/v1/config")).status_code for _ in range(4)]
    assert codes[0] == 200 and codes[1] == 200
    assert 429 in codes
    limited = await client.get("/api/v1/config")
    assert limited.status_code == 429
    assert limited.headers["retry-after"]


async def test_health_is_never_rate_limited(client):
    rate_limiter.max_requests = 1
    rate_limiter.reset()
    for _ in range(5):
        assert (await client.get("/healthz")).status_code == 200


async def test_oversized_body_is_rejected(client, auth):
    big = "x" * (1024 * 1024 + 10)
    response = await client.post("/api/v1/agents", headers=auth,
                                 json={"id": "agt_big", "name": big, "role": "consumer",
                                       "paypal_email": "big@example.com"})
    assert response.status_code in {413, 400}


async def test_nested_illegal_key_is_rejected(client, auth):
    response = await client.post("/api/v1/trades", headers=auth, json={
        "buyer_id": "agt_atlas",
        "job": {"type": "image_resize", "size": 10, "params": {"$ne": 1}},
    })
    assert response.status_code == 400
    assert "illegal key" in response.text


async def test_revoked_session_is_rejected(db, client, operator_token):
    headers = {"Authorization": f"Bearer {operator_token}"}
    assert (await client.get("/api/v1/agents", headers=headers)).status_code == 200
    me = await client.get("/api/v1/session/me", headers=headers)
    await revoke_session(db, me.json()["jti"])
    assert (await client.get("/api/v1/agents", headers=headers)).status_code == 401


async def test_expired_session_row_is_rejected(db, client):
    from datetime import datetime, timedelta, timezone

    token, session = await issue_session(db, "operator", 60)
    await db.users_sessions.update_one(
        {"jti": session.jti},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)}},
    )
    response = await client.get("/api/v1/agents", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_judge_quota_is_enforced(db, seeded, client, judge_token, monkeypatch):
    from app.services import trades as trades_service
    from tests.conftest import fake_dispatch

    monkeypatch.setattr(trades_service, "dispatch_job", fake_dispatch())
    me = await client.get("/api/v1/session/me", headers={"Authorization": f"Bearer {judge_token}"})
    jti = me.json()["jti"]
    await db.users_sessions.update_one({"jti": jti}, {"$set": {"quotas.scenarios_left": 1}})

    headers = {"Authorization": f"Bearer {judge_token}"}
    first = await client.post("/api/v1/scenarios/S1/run", headers=headers, json={})
    assert first.status_code == 201
    second = await client.post("/api/v1/scenarios/S1/run", headers=headers, json={})
    assert second.status_code == 429


async def test_judge_cannot_fund_or_settle(client, judge_token):
    headers = {"Authorization": f"Bearer {judge_token}"}
    funding = await client.post("/api/v1/funding", headers=headers,
                               json={"agent_id": "agt_atlas", "amount_micro": 10000})
    assert funding.status_code == 403
    settlement = await client.post("/api/v1/settlement/run", headers=headers, json={})
    assert settlement.status_code == 403


async def test_event_stream_requires_token(client):
    response = await client.get("/api/v1/events/stream")
    assert response.status_code == 401


async def test_invalid_amounts_are_rejected(client, auth):
    response = await client.post("/api/v1/funding", headers=auth,
                                 json={"agent_id": "agt_atlas", "amount_micro": -5})
    assert response.status_code == 422
    response = await client.post("/api/v1/funding", headers=auth,
                                 json={"agent_id": "agt_atlas", "amount_micro": 50_000_001})
    assert response.status_code == 422


async def test_unknown_agent_funding_is_404_or_400(client, auth):
    response = await client.post("/api/v1/funding", headers=auth,
                                 json={"agent_id": "agt_missing", "amount_micro": 10_000})
    assert response.status_code == 400
    assert "agent_not_found" in response.text
