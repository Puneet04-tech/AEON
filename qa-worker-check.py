import httpx, time

base = "https://aeon-lqc9.onrender.com"
r = httpx.post(base + "/api/v1/session/judge", json={}, timeout=60)
tok = r.json()["token"]
H = {"Authorization": "Bearer " + tok}

for i in range(4):
    r = httpx.get(base + "/api/v1/workers/health", headers=H, timeout=60)
    ws = r.json()["workers"]
    good = [w["worker_id"] for w in ws if w.get("healthy")]
    bad = [w.get("error") for w in ws if not w.get("healthy")]
    print(f"attempt {i+1}: healthy={good} bad={bad}")
    if not bad:
        break
    time.sleep(20)
