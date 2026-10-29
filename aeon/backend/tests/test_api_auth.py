"""Session, role enforcement and input-hardening tests."""
import pytest


async def test_health_and_config_are_public(client):
    health = await client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["service"] == "aeon-api"

    config = await client.get("/api/v1/config")
    assert config.status_code == 200
    body = config.json()
    assert body["paypal_env"] == "sandbox"
    assert "sandbox" in body["disclosures"][0].lower()


async def test_protected_route_requires_token(client):
    response = await client.get("/api/v1/agents")
    assert response.status_code == 401


async def test_bad_token_is_rejected(client):
    response = await client.get("/api/v1/agents", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


async def test_login_wrong_password(client):
    response = await client.post("/api/v1/session/login", json={"password": "wrong"})
    assert response.status_code == 401


async def test_login_and_me(client):
    response = await client.post("/api/v1/session/login", json={"password": "test-operator-password"})
    assert response.status_code == 200
    token = response.json()["token"]
    me = await client.get("/api/v1/session/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "operator"


async def test_judge_cannot_use_operator_endpoints(client, judge_token):
    headers = {"Authorization": f"Bearer {judge_token}"}
    response = await client.post("/api/v1/control/kill-switch", json={"active": True}, headers=headers)
    assert response.status_code == 403


async def test_operator_can_read_agents(seeded, client, auth):
    response = await client.get("/api/v1/agents", headers=auth)
    assert response.status_code == 200
    agents = response.json()["agents"]
    assert len(agents) >= 5
    assert all("balances" in agent for agent in agents)


async def test_create_agent_is_idempotent(seeded, client, auth):
    payload = {
        "id": "agt_new", "name": "New Agent", "role": "consumer",
        "paypal_email": "new-agent@example.com",
    }
    headers = {**auth, "Idempotency-Key": "created-agent-key-1"}
    first = await client.post("/api/v1/agents", json=payload, headers=headers)
    assert first.status_code == 201, first.text
    second = await client.post("/api/v1/agents", json=payload, headers=headers)
    assert second.status_code == 201
    assert second.json().get("_replayed") is True

    conflict = await client.post("/api/v1/agents", json={**payload, "name": "Other"}, headers=headers)
    assert conflict.status_code == 409


async def test_nosql_injection_keys_are_rejected(seeded, client, auth):
    response = await client.post("/api/v1/agents", json={"id": "agt_x", "name": "x", "role": "consumer",
                                                         "paypal_email": "a@b.com",
                                                         "$where": "1==1"}, headers=auth)
    assert response.status_code == 400
    assert "illegal key" in response.text


async def test_policy_patch_and_pause(seeded, client, auth):
    patch = await client.patch("/api/v1/agents/agt_atlas/policy",
                               json={"per_trade_cap_micro": 1234}, headers=auth)
    assert patch.status_code == 200, patch.text
    agent = await client.get("/api/v1/agents/agt_atlas", headers=auth)
    assert agent.json()["policy"]["per_trade_cap_micro"] == 1234

    paused = await client.post("/api/v1/agents/agt_atlas/pause", headers=auth)
    assert paused.json()["status"] == "PAUSED"
    resumed = await client.post("/api/v1/agents/agt_atlas/resume", headers=auth)
    assert resumed.json()["status"] == "ACTIVE"


async def test_security_headers_present(client):
    response = await client.get("/healthz")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-request-id"]
