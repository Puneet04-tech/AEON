import httpx, time

base = "https://aeon-lqc9.onrender.com"
r = httpx.post(base + "/api/v1/session/login", json={"password": "demo-operator"}, timeout=60)
tok = r.json()["token"]
H = {"Authorization": "Bearer " + tok}

r = httpx.get(base + "/api/v1/agents", headers=H, timeout=60)
agents = r.json()["agents"]
buyer = next(a for a in agents if a["role"] == "consumer")
seller = next(a for a in agents if a["role"] == "provider" and a["status"] == "ACTIVE")

job = {"type": "image_resize", "size": 307200,
       "params": {"width": 320, "height": 240}, "deadline_s": 30}
t0 = time.time()
r = httpx.post(base + "/api/v1/trades",
               headers={**H, "Idempotency-Key": "llmfin" + str(int(time.time()))},
               json={"buyer_id": buyer["id"], "seller_id": seller["id"], "job": job},
               timeout=180)
t = r.json()
tid = t.get("id")
print("FULL TRADE:", round(time.time() - t0, 1), "s ->", t.get("state"), tid)

r = httpx.get(base + f"/api/v1/trades/{tid}", headers=H, timeout=60)
d = r.json()
tr = d.get("negotiation_transcript") or []
print("negotiation:", len(tr), "moves | rounds:", max((x['round'] for x in tr), default=0),
      "| sources:", {x['llm'].get('source') for x in tr})
for row in tr:
    print(f"  r{row['round']} {row['from'][:12]:12s} {row['offer']['price_micro']:>8} "
          f"| {row['reasoning_text'][:58]}")

m = d.get("metering") or {}
print("executed on:", m.get("worker_id"), "cpu_s:", m.get("cpu_s"),
      "| sla breached:", (d.get("sla") or {}).get("breached"))

r = httpx.get(base + "/api/v1/ledger/invariant", headers=H, timeout=60)
inv = r.json()
print("INVARIANT ok:", inv.get("ok"), "| sum:", inv.get("sum_micro"),
      "| txns:", inv.get("transactions"))
