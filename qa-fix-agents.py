import httpx, time

base = "https://aeon-lqc9.onrender.com"
r = httpx.post(base + "/api/v1/session/login", json={"password": "demo-operator"}, timeout=60)
tok = r.json()["token"]
H = {"Authorization": "Bearer " + tok}

# Resume BOTH providers repeatedly until ACTIVE (bond may need refill)
r = httpx.get(base + "/api/v1/agents", headers=H, timeout=60)
agents = r.json()["agents"]
for a in agents:
    if a["role"] == "provider" and a["status"] != "ACTIVE":
        rr = httpx.post(base + f"/api/v1/agents/{a['id']}/resume",
                        headers={**H, "Idempotency-Key": "rx" + a["id"] + str(int(time.time()))},
                        json="{}", timeout=60)
        print("resume", a["name"], rr.status_code)

time.sleep(2)
r = httpx.get(base + "/api/v1/agents", headers=H, timeout=60)
agents = r.json()["agents"]
for a in agents:
    b = a.get("balances") or {}
    print(a["name"], a["role"], a["status"], "avail:", b.get("available_micro"), "bond:", b.get("bond_micro"))
