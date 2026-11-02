# AEON: project guide and deployment flow

## 1. AEON in simple language

AEON is a clearing-house dashboard for AI agents that buy and sell compute work.
It is a demo financial workflow: money is represented as integer micro-USD
(`1 USD = 1,000,000`), and PayPal is sandbox-only or simulated when credentials
are not configured.

The normal flow is:

1. An operator signs in or creates an account.
2. The dashboard loads agents, balances, workers, trades, ledger entries, payouts,
   approvals, audit records, and live events.
3. The operator chooses a consumer and provider, then clicks **Run Trade**.
4. The API validates policy and budget rules, negotiates a deterministic price,
   locks escrow, and signs a compute job.
5. A worker executes the job and returns a signed, checksummed result.
6. AEON verifies the result, settles the ledger, and displays the trade and event
   history.
7. The operator can fund agents, approve high-value actions, and run settlement.

Judge mode creates a time-limited, scenario-limited session for demonstrations.
It cannot be used as an operator account.

## 2. Project structure

```text
aeon/
  backend/       FastAPI API, MongoDB persistence, auth, ledger, policies
  worker/        Small FastAPI compute worker services
  dashboard/     React + TypeScript + Vite operator console
  docs/          Project documentation and screenshots
  postman/       API request collections
  scripts/       Development and verification helpers
  render.yaml    Render blueprint for API and two workers
```

### Backend

The backend owns authentication, sessions, agents, trades, negotiations,
guardrails, escrow, ledger entries, settlement batches, PayPal sandbox/mock
funding, audit records, event streaming, and worker dispatch. MongoDB stores
accounts, sessions, agents, trades, jobs, events, and financial records.

### Workers

Atlas and Boreal are identical worker applications with different IDs. The API
selects a worker through `WORKER_URLS`. Every job is authenticated with
`HMAC_SHARED_SECRET`; the worker rejects a mismatched secret or replayed request.

### Dashboard

The dashboard is a single-page React application. It stores the session token in
browser local storage, sends `Authorization: Bearer <token>` on protected calls,
uses HTTP polling as a refresh fallback, and uses an SSE stream for live events.

## 3. Local development

### Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB Atlas or local MongoDB
- One terminal for the API, two for workers, and one for the dashboard

Copy `.env.example` to `.env` inside `aeon` and set at least:

```dotenv
MONGODB_URI=your-mongodb-uri
MONGODB_DB=aeon
SESSION_SECRET=long-random-session-secret
HMAC_SHARED_SECRET=long-random-worker-secret
WORKER_URLS=http://localhost:8001,http://localhost:8002
ALLOWED_ORIGIN=http://localhost:5173
LLM_MODE=off
AUTO_SEED=true
```

Never commit `.env`.

### Start the services

Backend:

```powershell
cd aeon\backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Worker Atlas:

```powershell
cd aeon\worker
pip install -r requirements.txt
$env:WORKER_ID="worker-atlas"
$env:WORKER_PORT="8001"
$env:HMAC_SHARED_SECRET="same-secret-as-backend"
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Worker Boreal uses the same command with `WORKER_ID=worker-boreal` and port
`8002`.

Dashboard:

```powershell
cd aeon\dashboard
npm ci
npm run dev
```

Open `http://localhost:5173`. The Vite proxy sends `/api` requests to
`http://127.0.0.1:8000`.

### First dashboard actions

1. Use **Create account** for a normal operator account, or **Enter judge mode**
   for a guided demo.
2. Confirm the worker pill reports `2/2`.
3. Open the lightning button (**Run Trade**).
4. Select a consumer and provider, choose a job, and submit.
5. Watch the trade move through `CREATED`, `AGREED`, `ESCROWED`, `DISPATCHED`,
   `DELIVERED`, `VERIFIED`, and finally `SETTLED`.
6. Select the trade row to inspect negotiation details and the event stream.
7. Use **Fund Agent** for sandbox/mock funding.
8. Use **Settle** to net balances and create a payout batch.
9. Use **Approvals** for actions above the configured approval threshold.
10. Use **Audit**, **Ledger**, and **Invariant** views to verify accounting.

## 4. Deploying on Render and Vercel

Docker is intentionally not part of this deployment path. Render runs the
Python services directly, and Vercel builds the dashboard as static assets.

### A. Deploy the API and workers to Render

1. Push the repository to GitHub.
2. In Render, choose **New > Blueprint** and select this repository.
3. Render reads `render.yaml` and creates:
   - `aeon-api`
   - `aeon-worker-atlas`
   - `aeon-worker-boreal`
4. In the Render dashboard, set the secret values:
   - `MONGODB_URI`
   - `HMAC_SHARED_SECRET` (the same value on API and both workers)
   - `OPERATOR_PASSWORD_HASH` (recommended for production)
   - PayPal sandbox credentials if real sandbox checkout is desired
   - Cloudflare credentials only if `LLM_MODE=live`
5. Set `ALLOWED_ORIGIN` temporarily to the future Vercel URL, then update it
   after Vercel provides the final domain.
6. Verify:
   - `https://aeon-api.onrender.com/healthz`
   - `https://aeon-worker-atlas.onrender.com/health`
   - `https://aeon-worker-boreal.onrender.com/health`
7. Confirm API `WORKER_URLS` exactly matches both worker URLs.

For a safe initial deployment, use `LLM_MODE=off` and `PAYPAL_MODE=mock`.
This keeps the system deterministic and avoids requiring external credentials.

### B. Deploy the dashboard to Vercel

1. In Vercel, choose **Add New Project** and import this repository.
2. Set **Root Directory** to `aeon/dashboard`.
3. Use:
   - Framework preset: **Vite**
   - Install command: `npm ci`
   - Build command: `npm run build`
   - Output directory: `dist`
4. Add the environment variable:

   ```text
   VITE_API_BASE=https://aeon-api.onrender.com
   ```

5. Deploy. `dashboard/vercel.json` keeps client-side routes working.
6. Copy the final Vercel URL into Render's API `ALLOWED_ORIGIN`.
7. Redeploy the API and test signup, login, refresh, judge mode, workers, and a
   complete trade from the Vercel dashboard.

If a custom Vercel domain is added, include that exact origin in
`ALLOWED_ORIGIN` (scheme plus host, without a trailing slash).

## 5. Production checklist

- Use strong, different `SESSION_SECRET` and `HMAC_SHARED_SECRET` values.
- Use a least-privilege MongoDB user and restrict Atlas network access.
- Do not commit `.env`, API keys, PayPal secrets, or worker logs.
- Keep `PAYPAL_ENV=sandbox`; AEON does not support live money movement.
- Prefer `OPERATOR_PASSWORD_HASH` over `OPERATOR_PASSWORD`.
- Keep `LLM_MODE=off` until Cloudflare credentials are configured and tested.
- Verify all three Render health endpoints.
- Verify the browser Network tab sends `Authorization: Bearer ...`.
- Create one test account, reload the page, and confirm the session persists.
- Run one trade and confirm it reaches `SETTLED` with worker metering.
- Review the Ledger invariant and Audit pages after the test.
- Monitor Render logs for worker signature errors, MongoDB errors, and 429s.

## 6. Common problems

### Agent selectors are empty

The dashboard cannot load `/api/v1/agents`. Check `VITE_API_BASE`, the browser
Network tab, the session token, and API `ALLOWED_ORIGIN`.

### Trade is created but fails with `signature_rejected`

The API and both workers do not share the exact same `HMAC_SHARED_SECRET`.
Update all three services and redeploy/restart them.

### Dashboard returns to login after refresh

Confirm the API returns `200` for `/api/v1/session/me`, the Vercel origin is in
`ALLOWED_ORIGIN`, and browser storage contains `aeon.token`, `aeon.role`, and
`aeon.quotas`.

### Render workers are unhealthy

Check each worker's `WORKER_ID`, `HMAC_SHARED_SECRET`, health path, and service
port. Render supplies `$PORT`; the start command in `render.yaml` uses it.

### PayPal funding does not open checkout

Use `PAYPAL_MODE=mock` for a no-credential demo, or configure valid PayPal
sandbox credentials and return/cancel URLs. No real money is moved.

## 7. Useful API and validation commands

```powershell
# API health
curl.exe https://aeon-api.onrender.com/healthz

# Worker health
curl.exe https://aeon-worker-atlas.onrender.com/health
curl.exe https://aeon-worker-boreal.onrender.com/health

# Dashboard build
cd aeon\dashboard
npm run build

# Backend tests
cd aeon\backend
pytest -q
```

