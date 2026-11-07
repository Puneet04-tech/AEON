import httpx, time, json

base = "https://aeon-lqc9.onrender.com"
r = httpx.post(base + "/api/v1/session/login", json={"password": "demo-operator"}, timeout=60)
tok = r.json()["token"]
H = {"Authorization": "Bearer " + tok}

r = httpx.get(base + "/api/v1/trades/trd_d7de06d599e149e1bd5a", headers=H, timeout=60)
d = r.json()
print("failure:", json.dumps(d.get("failure"), indent=1))
