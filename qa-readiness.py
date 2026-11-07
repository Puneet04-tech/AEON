import httpx, time, json

base = "https://aeon-lqc9.onrender.com"
r = httpx.post(base + "/api/v1/session/login", json={"password": "demo-operator"}, timeout=60)
tok = r.json()["token"]
H = {"Authorization": "Bearer " + tok}

# Ready check detail: what does the API itself say about workers?
r = httpx.get(base + "/api/v1/hackathon/readiness", headers=H, timeout=60)
rd = r.json()
print("ready:", rd.get("ready"))
for c in rd.get("checks", []):
    print(" ", json.dumps(c)[:160])
