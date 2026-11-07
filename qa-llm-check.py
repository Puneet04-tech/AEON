import httpx, time

base = "https://aeon-lqc9.onrender.com"
r = httpx.post(base + "/api/v1/session/judge", json={}, timeout=60)
tok = r.json()["token"]
H = {"Authorization": "Bearer " + tok}

# 1. Full transcript of the failed trade
r = httpx.get(base + "/api/v1/trades/trd_c6781110c179447b84c5", headers=H, timeout=60)
d = r.json()
for row in (d.get("negotiation_transcript") or []):
    llm = row.get("llm", {})
    print(f" r{row['round']} {row['from'][:14]:14s} {row['offer']['price_micro']:>9} "
          f"| {row['reasoning_text'][:70]:70s} | {llm.get('source')}/{llm.get('model')}")

# 2. Worker health detail
r = httpx.get(base + "/api/v1/workers/health", headers=H, timeout=60)
for w in r.json()["workers"]:
    print("worker:", w.get("worker_id"), "healthy=", w.get("healthy"), "err=", w.get("error"))

# 3. Agent statuses (maybe a provider is suspended)
r = httpx.get(base + "/api/v1/agents", headers=H, timeout=60)
for a in r.json()["agents"]:
    if a["role"] == "provider":
        print("provider:", a["name"], a["status"], "bond:", a.get("balances", {}).get("bond_micro"))
