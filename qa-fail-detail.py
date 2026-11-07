import httpx, time, json

base = "https://aeon-lqc9.onrender.com"
r = httpx.post(base + "/api/v1/session/login", json={"password": "demo-operator"}, timeout=60)
tok = r.json()["token"]
H = {"Authorization": "Bearer " + tok}

r = httpx.get(base + "/api/v1/trades/trd_2b6eb0fcf4204509a5df", headers=H, timeout=60)
d = r.json()
print("failure:", d.get("failure"))
print("state:", d.get("state"))
print("links:", d.get("links"))
m = d.get("metering")
print("metering:", m)

# check events for this trade
r = httpx.get(base + "/api/v1/events/recent?since=0", headers=H, timeout=60)
evts = [e for e in r.json().get("events", []) if e.get("trade_id") == "trd_2b6eb0fcf4204509a5df"]
for e in sorted(evts, key=lambda x: x["seq"]):
    print(e["seq"], e["type"], json.dumps(e.get("payload", {}))[:150])
