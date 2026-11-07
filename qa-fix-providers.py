import httpx, time

base = "https://aeon-lqc9.onrender.com"
r = httpx.post(base + "/api/v1/session/login", json={"password": "demo-operator"}, timeout=60)
tok = r.json()["token"]
H = {"Authorization": "Bearer " + tok}

r = httpx.get(base + "/api/v1/agents", headers=H, timeout=60)
for a in r.json()["agents"]:
    if a["role"] == "provider":
        b = a.get("balances") or {}
        print(a["id"], a["name"], a["status"], "bond:", b.get("bond_micro"))

# resume both providers (operator)
for aid in ["agt_cirrus", "agt_dunlin"]:
    r = httpx.post(base + f"/api/v1/agents/{aid}/resume",
                   headers={**H, "Idempotency-Key": "resume2" + aid},
                   json="{}", timeout=60)
    print(aid, "resume:", r.status_code)
