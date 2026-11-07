import httpx, time

base = "https://aeon-lqc9.onrender.com"
r = httpx.post(base + "/api/v1/session/login", json={"password": "demo-operator"}, timeout=60)
tok = r.json()["token"]
H = {"Authorization": "Bearer " + tok}

r = httpx.get(base + "/api/v1/agents", headers=H, timeout=60)
agents = r.json()["agents"]
for a in agents:
    print(a["name"], a["role"], a["status"])

providers = [a for a in agents if a["role"] == "provider" and a["status"] == "ACTIVE"]
consumers = [a for a in agents if a["role"] == "consumer"]
if not providers:
    print("NO ACTIVE PROVIDER — resuming all")
    for a in agents:
        if a["role"] == "provider":
            rr = httpx.post(base + f"/api/v1/agents/{a['id']}/resume",
                            headers={**H, "Idempotency-Key": "r3" + a["id"]}, json="{}", timeout=60)
            print("resume", a["name"], rr.status_code)
    providers = [a for a in agents if a["role"] == "provider"]

buyer, seller = consumers[0], providers[0]
job = {"type": "image_resize", "size": 307200,
       "params": {"width": 320, "height": 240}, "deadline_s": 30}
t0 = time.time()
r = httpx.post(base + "/api/v1/trades",
               headers={**H, "Idempotency-Key": "fx" + str(int(time.time()))},
               json={"buyer_id": buyer["id"], "seller_id": seller["id"], "job": job},
               timeout=180)
t = r.json()
tid = t.get("id")
print("TRADE:", round(time.time() - t0, 1), "s ->", t.get("state"), tid)
print("failure:", t.get("failure"))
if tid and t.get("state") == "SETTLED":
    rr = httpx.get(base + f"/api/v1/trades/{tid}", headers=H, timeout=60)
    d = rr.json()
    tr = d.get("negotiation_transcript") or []
    print("NEGOTIATION:", len(tr), "moves, sources:", {x['llm'].get('source') for x in tr})
    for row in tr:
        print(f"  r{row['round']} {row['offer']['price_micro']:>8} {row['reasoning_text'][:60]}")
    m = d.get("metering") or {}
    print("EXEC:", m.get("worker_id"), "cpu_s:", m.get("cpu_s"))
