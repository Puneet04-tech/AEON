"""MCP treasurer endpoint, treasurer planning and demo reset."""
import pytest

from app.ledger.service import LedgerService
from app.services import trades as trades_service
from tests.conftest import fake_dispatch

JOB = {"type": "image_resize", "size": 640 * 480, "params": {}, "deadline_s": 30}


def rpc(method, params=None, request_id=1):
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}


async def test_mcp_requires_auth(client):
    response = await client.post("/mcp", json=rpc("initialize"))
    assert response.status_code == 401


async def test_mcp_initialize_and_catalogue(seeded, client, auth):
    init = await client.post("/mcp", json=rpc("initialize"), headers=auth)
    assert init.status_code == 200
    body = init.json()
    assert body["result"]["protocolVersion"] == "2024-11-05"
    assert body["result"]["serverInfo"]["name"] == "aeon-treasurer"

    tools = await client.post("/mcp", json=rpc("tools/list", request_id=2), headers=auth)
    names = {tool["name"] for tool in tools.json()["result"]["tools"]}
    assert {"aeon_list_orders", "aeon_propose_settlement", "aeon_invariant"} <= names

    catalogue = await client.get("/api/v1/mcp/tools", headers=auth)
    assert catalogue.status_code == 200
    assert len(catalogue.json()["tools"]) == 6


async def test_mcp_invariant_tool(seeded, client, auth):
    response = await client.post("/mcp", json=rpc("tools/call", {
        "name": "aeon_invariant", "arguments": {}}), headers=auth)
    payload = response.json()["result"]
    assert payload["isError"] is False
    import json

    report = json.loads(payload["content"][0]["text"])
    assert report["ok"] is True


async def test_mcp_balances_tool(seeded, client, auth):
    response = await client.post("/mcp", json=rpc("tools/call", {
        "name": "aeon_ledger_balances", "arguments": {}}), headers=auth)
    import json

    data = json.loads(response.json()["result"]["content"][0]["text"])
    assert data["treasury_funds_micro"] > 0
    assert any(agent["agent_id"] == "agt_atlas" for agent in data["agents"])


async def test_mcp_unknown_tool_and_method(seeded, client, auth):
    unknown_tool = await client.post("/mcp", json=rpc("tools/call", {
        "name": "aeon_wire_money", "arguments": {}}), headers=auth)
    assert unknown_tool.json()["error"]["code"] == -32602

    unknown_method = await client.post("/mcp", json=rpc("resources/list"), headers=auth)
    assert unknown_method.json()["error"]["code"] == -32601


async def test_mcp_parse_error_and_batch(seeded, client, auth):
    bad = await client.post("/mcp", content=b"{not json", headers={**auth, "Content-Type": "application/json"})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == -32700

    batch = await client.post("/mcp", json=[rpc("ping", request_id=1), rpc("tools/list", request_id=2)],
                              headers=auth)
    assert batch.status_code == 200
    settled = batch.json()
    assert len(settled) == 2


async def test_treasurer_plan_follows_settlement_reality(db, seeded, client, auth, monkeypatch):
    monkeypatch.setattr(trades_service, "dispatch_job", fake_dispatch())
    await trades_service.run_trade(db, "agt_atlas", JOB, seller_id="agt_cirrus")

    plan = await client.get("/api/v1/treasurer/plan", headers=auth)
    assert plan.status_code == 200
    body = plan.json()
    assert body["totals"]["amount_micro"] > 0
    assert body["treasurer"]["llm"]["source"] == "fallback"  # LLM_MODE=off in tests
    assert body["treasurer"]["guardrail"]["passed"] in {True, False}
    assert body["treasurer"]["recommend"] is True


async def test_treasurer_orders_and_transactions(seeded, client, auth, db):
    from app.services import funding as funding_service

    funding = await funding_service.create_funding(db, "agt_atlas", 1_000_000)
    await funding_service.capture_funding(db, funding["id"])

    orders = await client.get("/api/v1/treasurer/orders", headers=auth)
    assert orders.json()["orders"][0]["state"] in {"CREATED", "CAPTURED"}

    transactions = await client.get("/api/v1/treasurer/transactions", headers=auth)
    kinds = {row["kind"] for row in transactions.json()["transactions"]}
    assert "capture" in kinds


async def test_mcp_settlement_tool_cannot_move_money(seeded, client, auth, db):
    from app.services import funding as funding_service

    funding = await funding_service.create_funding(db, "agt_atlas", 1_000_000)
    await funding_service.capture_funding(db, funding["id"])
    before = await LedgerService(db).treasury_funds_micro()

    response = await client.post("/mcp", json=rpc("tools/call", {
        "name": "aeon_propose_settlement", "arguments": {}}), headers=auth)
    assert response.status_code == 200
    assert await LedgerService(db).treasury_funds_micro() == before
    assert (await db.settlements.count_documents({})) == 0


async def test_demo_reset_is_operator_only_and_reseeds(db, seeded, client, auth, judge_token):
    import contextlib

    from app.services import trades as trades_service_mod

    with contextlib.suppress(Exception):
        await trades_service_mod.run_trade(db, "agt_atlas", JOB, seller_id="agt_cirrus")

    judge = await client.post("/api/v1/demo/reset", headers={"Authorization": f"Bearer {judge_token}"})
    assert judge.status_code == 403

    reset = await client.post("/api/v1/demo/reset", headers=auth)
    assert reset.status_code == 200, reset.text
    assert reset.json()["agents"] == 5
    assert await db.trades.count_documents({}) == 0
    ledger = LedgerService(db)
    # Reset must also clear the ledger idempotency headers, otherwise reseeding
    # silently replays as a duplicate and every balance comes back zero.
    assert await ledger.balance("agt_atlas") == 25_000_000
    assert await ledger.treasury_funds_micro() > 0
    assert (await ledger.invariant())["ok"] is True


async def test_demo_reset_refused_while_kill_switch_armed(seeded, client, auth, db):
    from app.guardrails import policy

    await policy.set_kill_switch(db, True, "test")
    response = await client.post("/api/v1/demo/reset", headers=auth)
    assert response.status_code == 409
