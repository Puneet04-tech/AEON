#!/usr/bin/env python3
"""Post-deployment smoke test for AEON.

Runs against a *running* API (local or deployed) and verifies the things that
only break once real credentials are in place: PayPal order + capture + webhook
signature handling, netting and payout reconciliation, negotiation and the
ledger invariant.

    python scripts/smoke.py --base-url http://127.0.0.1:8000 \
        --password "$OPERATOR_PASSWORD"

Exit code 0 means every check passed. Failures print the HTTP status and body so
the cause is visible without reading logs.
"""
import argparse
import json
import sys
import time
import uuid
from typing import Any, Dict, Optional

import httpx


class Smoke:
    def __init__(self, base_url: str, password: str, timeout: float = 90.0):
        self.base = base_url.rstrip("/")
        self.password = password
        self.timeout = timeout
        self.client = httpx.Client(base_url=self.base, timeout=timeout)
        self.token: Optional[str] = None
        self.failures: list[str] = []
        self.passed = 0

    # ------------------------------------------------------------------ utils
    def headers(self, idempotent: bool = False) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if idempotent:
            headers["Idempotency-Key"] = uuid.uuid4().hex
        return headers

    def check(self, name: str, ok: bool, detail: Any = "") -> None:
        if ok:
            self.passed += 1
            print(f"  PASS  {name}")
        else:
            self.failures.append(name)
            print(f"  FAIL  {name}  {str(detail)[:400]}")

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        kwargs.setdefault("headers", self.headers(kwargs.pop("idempotent", False)))
        return self.client.request(method, path, **kwargs)

    # ------------------------------------------------------------------ steps
    def login(self) -> None:
        response = self.client.post("/api/v1/session/login", json={"password": self.password})
        self.check("operator login", response.status_code == 200, response.text)
        if response.status_code == 200:
            self.token = response.json()["token"]

    def config(self) -> dict:
        response = self.request("GET", "/api/v1/config")
        self.check("public config", response.status_code == 200, response.text)
        return response.json() if response.status_code == 200 else {}

    def health(self) -> None:
        response = self.client.get("/healthz")
        self.check("healthz", response.status_code == 200 and response.json().get("mongo") is True,
                   response.text)

    def invariant(self) -> None:
        response = self.request("GET", "/api/v1/ledger/invariant")
        body = response.json() if response.status_code == 200 else {}
        self.check("ledger invariant balanced", body.get("ok") is True, body)

    def workers(self) -> None:
        response = self.request("GET", "/api/v1/workers/health")
        workers = response.json().get("workers", []) if response.status_code == 200 else []
        healthy = [w for w in workers if w.get("healthy")]
        self.check(f"workers healthy ({len(healthy)}/{len(workers)})", bool(healthy), workers)

    def scenario(self, name: str) -> dict:
        started = time.time()
        response = self.request("POST", f"/api/v1/scenarios/{name}/run", json={}, idempotent=True)
        elapsed = time.time() - started
        body = response.json() if response.status_code < 500 else {"detail": response.text}
        state = body.get("state")
        self.check(f"{name} completed in {elapsed:.1f}s", state == "COMPLETED",
                   body.get("error") or body.get("detail"))
        return body

    def funding_roundtrip(self, agent_id: str) -> None:
        order = self.request("POST", "/api/v1/funding",
                             json={"agent_id": agent_id, "amount_micro": 2_000_000}, idempotent=True)
        if order.status_code != 201:
            self.check("funding order created", False, order.text)
            return
        funding = order.json()
        self.check("funding order created", True)
        self.check("funding is real sandbox money", funding.get("mock") is False,
                   "mock adapter in use — PAYPAL_CLIENT_ID/SECRET not configured")

        capture = self.request("POST", f"/api/v1/funding/{funding['id']}/capture", idempotent=True)
        captured = capture.json() if capture.status_code == 200 else {}
        self.check("capture credited the ledger", captured.get("state") == "CAPTURED", capture.text)

        balances = self.request("GET", f"/api/v1/agents/{agent_id}").json()
        self.check("agent balance visible", balances.get("balances", {}).get("available_micro", 0) > 0,
                   balances.get("balances"))

    def settlement(self) -> None:
        batch = self.request("POST", "/api/v1/settlement/run", json={"has_approval": True}, idempotent=True)
        body = batch.json() if batch.status_code < 500 else {"detail": batch.text}
        state = body.get("state")
        if state is None and "nothing_to_settle" in str(body.get("detail", "")):
            # Correct answer when every opted-in agent was already paid: nothing is owed.
            self.check("settlement submitted (nothing owed)", True)
            return
        if state == "AWAITING_APPROVAL":
            approvals = self.request("GET", "/api/v1/approvals?state=PENDING").json().get("approvals", [])
            if approvals:
                decided = self.request("POST", f"/api/v1/approvals/{approvals[0]['id']}/decision",
                                       json={"decision": "APPROVED", "reason": "smoke test"}, idempotent=True)
                body = decided.json().get("execution", decided.json())
                state = body.get("state")
        self.check("settlement submitted", state in {"SUBMITTED", "SUCCEEDED", "PARTIAL"}, body)
        self.check("settlement used real PayPal", body.get("simulated") is False,
                   "simulated payout adapter in use")

        payouts = self.request("GET", "/api/v1/payouts?limit=20").json().get("payouts", [])
        self.check("payout items recorded", bool(payouts), payouts)
        if payouts:
            self.check("payout item has a PayPal id", all(p.get("paypal_item_id") for p in payouts),
                       payouts[:2])

    def mcp(self) -> None:
        init = self.request("POST", "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.check("MCP initialize", init.status_code == 200 and "result" in init.json(), init.text)
        call = self.request("POST", "/mcp", json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "aeon_invariant", "arguments": {}}})
        body = call.json() if call.status_code == 200 else {}
        ok = body.get("result", {}).get("isError") is False
        self.check("MCP invariant tool", ok, body)

    # -------------------------------------------------------------------- run
    def run(self, include_payments: bool, include_settlement: bool) -> int:
        print(f"AEON smoke test against {self.base}\n")
        self.health()
        self.login()
        if not self.token:
            return self.report()

        config = self.config()
        print(f"  info  paypal_mode={config.get('paypal_mode')} llm_mode={config.get('llm_mode')}\n")
        self.workers()
        self.mcp()
        self.invariant()

        self.scenario("S1")
        self.invariant()
        self.scenario("S2")
        self.scenario("S3")
        self.invariant()

        if include_payments:
            agents = self.request("GET", "/api/v1/agents").json().get("agents", [])
            buyer = next((a["id"] for a in agents if a["role"] == "consumer"), "agt_atlas")
            self.funding_roundtrip(buyer)

        if include_settlement:
            self.scenario("S4")
            self.settlement()

        self.invariant()
        return self.report()

    def report(self) -> int:
        total = self.passed + len(self.failures)
        print(f"\n{self.passed}/{total} checks passed")
        if self.failures:
            print("failed: " + ", ".join(self.failures))
            return 1
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AEON post-deployment smoke test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--password", default="demo-operator")
    parser.add_argument("--skip-payments", action="store_true",
                        help="skip PayPal capture checks (mock mode still runnable)")
    parser.add_argument("--skip-settlement", action="store_true")
    args = parser.parse_args()

    smoke = Smoke(args.base_url, args.password)
    try:
        return smoke.run(include_payments=not args.skip_payments,
                         include_settlement=not args.skip_settlement)
    except httpx.HTTPError as exc:
        print(f"transport error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
