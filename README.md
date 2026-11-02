# AEON — Agent-to-Agent Settlement Network for Shared Compute

AEON is a clearing house for AI agents. Each agent represents a compute provider or a compute
consumer. Agents negotiate a price, run a real job on a real worker, and record the obligation in a
double-entry ledger. Money enters through PayPal checkout, trades net out inside the ledger, and
value leaves through a single PayPal Payouts batch — all under limits a human sets.

**Built for the PayPal AI Hackathon. PayPal is sandbox only: no real money moves.**

---

## The problem it addresses

A job worth four cents cannot be settled on card rails; agreeing a price, checking the work and
paying is more work than the job is worth; strangers do not trust each other; and nobody sensible
gives an autonomous agent an unbounded wallet. AEON answers each of those with one mechanism:
agents trade inside a ledger, a human owns the limits, and PayPal only sees the netted totals.

## Complete feature set

### Agent commerce

- Consumer and provider agent registry with status, region, capabilities, balances, policies, and
  PayPal receiver metadata.
- Provider selection using price, availability, uptime, verification history, and reputation.
- Multi-round negotiation with deterministic fallback when live AI is disabled.
- Machine-readable guardrails for price bands, per-trade limits, daily limits, allowlists, velocity,
  approvals, and retry behavior.
- Signed HMAC worker dispatch with replay protection and request timeouts.
- Real Pillow image-resize and NumPy matrix-multiply jobs executed by separate software workers.

### Proof-carrying execution

- Portable evidence envelope for every delivered job.
- Input and output digests, checksum, worker identity, runtime version, timestamps, CPU time, wall
  time, job type, and result shape.
- Consumer-side checksum and result-shape verification.
- Independent deterministic verification by a second worker when available.
- Explicit verification levels: independent deterministic verification or signed-execution fallback.
- Software-only corruption mode for demonstrating rejected results and failure handling.
- Evidence, verification checks, and provider-selection reasons are visible in the dashboard.

### Money, trust, and operations

- Integer micro-USD accounting with a balanced double-entry ledger.
- Escrow, settlement, treasury netting, provider bonds, penalties, loans, reservations, and dust
  handling.
- PayPal sandbox Orders, capture, Payouts, webhook signature verification, reconciliation, and
  idempotency.
- Evidence-backed disputes with a dedicated `agent_dispute_hold` account and refund/release
  resolution.
- Evidence-windowed provider reputation based on success, verification, and dispute history.
- Human approvals, agent pause/resume, audit log, emergency kill switch, and worker chaos controls.
- Readiness diagnostics covering PayPal, workers, receivers, evidence, and ledger integrity.
- Judge mode with guided scenarios and a limited time/run quota.
- Responsive dashboard with React Flow topology, AG Grid data views, event stream, trade drawer,
  ledger, payouts, agents, approvals, audit, readiness, and dark/light theme controls.

### Reliability and security

- Session persistence across refreshes and protected API requests.
- Request timeouts and explicit error notifications instead of indefinite UI hangs.
- Idempotency keys on state-changing requests and duplicate webhook protection.
- MongoDB indexes and validators for ledger, evidence, verification, dispute, and wallet data.
- Secrets kept in environment variables; Docker is not part of the deployment path.

## What makes AEON novel

AEON does not claim to invent agent marketplaces, compute marketplaces, escrow, or machine
payments. Those categories already exist. Its differentiating product layer is the complete,
transaction-level loop:

```text
policy → provider selection → negotiation → escrow → execution evidence
→ independent verification → reputation → dispute hold → settlement
```

Most adjacent products emphasize one part of that loop:

| Existing reference | Primary focus | AEON's difference |
|---|---|---|
| [Fetch.ai Agentverse](https://www.fetch.ai/agentverse) | Agent hosting, discovery, and communication | AEON records and governs the financial and evidence outcome of a specific job |
| [SingularityNET](https://marketplace.singularity.io/) | AI-service marketplace and service payments | AEON adds worker-level evidence, verification checks, dispute accounting, and reputation feedback |
| [Akash](https://akash.network/docs/learn/core-concepts/providers-leases/) | Decentralized compute providers, leases, bids, and escrow | AEON verifies application output, not only provider capacity or lease state |
| [Coinbase x402](https://docs.cdp.coinbase.com/x402/welcome) | Machine-to-machine payment transport over HTTP | AEON decides whether work deserves release, refund, dispute, or future trust |

The novelty is therefore **integration and operationalization**, not a claim of total technical
originality: AEON makes proof, policy, dispute, reputation, and settlement first-class parts of
agent commerce. The implemented MVP is software-only and intentionally excludes hardware
attestation. The full product direction is documented in
[`aeon/docs/NOVEL_APPROACH.md`](aeon/docs/NOVEL_APPROACH.md).

## Dashboard presentation flow

1. Enter **Judge mode** or sign in as an operator.
2. Confirm the top bar shows worker health, PayPal mode, and ledger invariant.
3. Use **Run Trade** to choose a consumer, provider, and job type.
4. Show the topology and event stream advancing through `created`, `escrowed`, `dispatched`,
   `delivered`, `verified`, and `settled`.
5. Select the trade row and show negotiation rounds, guardrail status, provider-selection reason,
   evidence metadata, checksum verification, and independent-worker agreement.
6. Use **Ledger** to show balanced postings and `INVARIANT 0 µUSD`.
7. Use **Treasurer**, **Approvals**, and **Payouts** to show human-controlled settlement operations.
8. Use the worker chaos control with corruption enabled, run another trade, and show rejection,
   rerouting, refund, or penalty handling.
9. Open **Open evidence dispute**, show funds moving to dispute hold, then choose **Refund** or
   **Release**.
10. Use **Audit** to show the immutable operational record and **DEMO READY** to show submission
    checks.

## What is real and what is simulated

| Element | Status | Detail |
|---|---|---|
| PayPal Orders, Payouts, webhooks | **Real (sandbox)** | Actual API calls, statuses and `verify-webhook-signature` |
| Agent decisions (offers, credit) | **Configurable** | Cloudflare Workers AI when enabled; otherwise deterministic fallback, always JSON-validated and clamped by guardrails |
| Compute jobs | **Real** | Image resize (Pillow) and matrix multiply (numpy) on separate workers, CPU metered with `process_time` |
| Ledger, escrow, netting, bonds, loans | **Real** | MongoDB double-entry ledger with invariants and idempotency |
| Weather input | **Real** | Open-Meteo current forecast, no API key |
| Energy price factor and "regions" | **Simulated** | Deterministic model over real temperature; labelled in the UI |
| Worker outage | **Simulated trigger, real handling** | Signed chaos switch → real health failure, reroute, penalty |
| Money | **Sandbox** | Stated in the console footer, `/api/v1/config` and this README |

If PayPal credentials are absent, funding and payouts are unavailable; the product does not
simulate money movement. The mock adapter is restricted to the isolated automated test harness.
Replayed LLM outputs (`LLM_MODE=replay`) are real recorded model outputs, sourced from
`.llm_cache.json` or the `llm_cache` collection.

## How a trade flows

```
consumer agent            orchestrator (API)                provider agent
     │                          │                                │
     │ 1. request job           │                                │
     ├─────────────────────────>│ 2. select provider (price/uptime)
     │                          │ 3. negotiate, max 3 rounds ────>│
     │<─────────────────────────┤    (LLM proposes, guardrails decide)
     │                          │ 4. escrow buyer balance
     │                          │ 5. signed job dispatch ────────>│ worker
     │                          │ 6. result + CPU seconds <──────┤
     │                          │ 7. verify digest, release escrow
     │                          │ 8. book: escrow → provider, fee → platform
     │                          │    SLA miss → bond penalty to buyer
```

Failure path: worker unreachable → refund buyer, penalty from the provider bond, reroute to another
provider, and after repeated late deliveries the provider is paused (bond suspension).

Money path: `PayPal checkout → ledger credit` and `netted balances → PayPal Payouts batch`.
Payouts always send from one treasury business account; agents never pay each other through PayPal.
That clearing-house shape is what makes micropayments economically sane.

## Quickstart

### Local development

```bash
cd backend
pip install -r requirements.txt
MONGODB_URI=memory:// OPERATOR_PASSWORD=demo-operator LLM_MODE=off \
HMAC_SHARED_SECRET=dev-hmac-secret-change-me uvicorn app.main:app --port 8000

cd ../worker
pip install -r requirements.txt
WORKER_ID=worker-atlas WORKER_PORT=8001 \
HMAC_SHARED_SECRET=dev-hmac-secret-change-me uvicorn app.main:app --port 8001
WORKER_ID=worker-boreal WORKER_PORT=8002 \
HMAC_SHARED_SECRET=dev-hmac-secret-change-me uvicorn app.main:app --port 8002

cd ../dashboard
npm install && npm run dev    # http://localhost:5173, proxies /api to :8000
```

Run the API, both workers, and dashboard in separate terminals. The API's
`HMAC_SHARED_SECRET` must match the value used by both workers. `MONGODB_URI=memory://` is an
explicit local demo mode: process-local and wiped on restart. For persistent local data, use
MongoDB Atlas and set `MONGODB_URI` in `backend/.env`.

### Tests

```bash
cd backend && python -m pytest -q     # 87 tests
cd worker  && python -m pytest -q     # 11 tests
cd dashboard && npx tsc --noEmit && npm run build
```

### Post-deployment smoke test

Once credentials are in place, verify the real paths against a running instance:

```bash
python scripts/smoke.py --base-url https://your-api.onrender.com --password "$OPERATOR_PASSWORD"
```

It runs S1-S3, an MCP tool call, a real funding order and capture, a settlement batch and the
invariant, then flags unavailable PayPal or fallback pricing. Exit code 0 means every check passed.

## Demo script (three minutes)

1. **S1** in the console: Atlas buys an image-resize job from Cirrus. Watch the negotiation rounds in
   the drawer, the escrow posting, the real result digest and the booking. Invariant chip stays `0`.
2. **S4**: treasury nets balances and pays Cirrus one PayPal sandbox payout. Payout items reconcile.
3. **S2**: inject chaos into Cirrus's worker, rerun. The job fails, the buyer is refunded, Cirrus's
   bond is penalised, Dunlin completes the reroute, and Cirrus borrows a credit line from Ember.
4. **S3**: Atlas reserves forward capacity priced from the real weather forecast (labelled simulated)
   and resells it to Boreal at a premium.
5. Open the **Approvals** tab, raise a settlement above the threshold, and approve it as a human.

Judge mode is metered: 30 minutes, 10 scenario runs.

## Architecture

```
dashboard (React + AG Grid + React Flow + SSE)
        │  /api/v1/*   (Bearer session, Idempotency-Key on writes)
        ▼
backend (FastAPI)  ── ledger / guardrails / negotiation / settlement / approvals
        │                     │                        │
        │ signed HMAC jobs    │ PayPal REST            │ MongoDB
        ▼                     ▼                        ▼
 worker A, worker B      Orders, Payouts,        agents, wallets,
 (Pillow, numpy)         webhooks                ledger_entries, trades,
                                                 negotiations, settlements,
                                                 payout_items, approvals,
                                                 loans, reservations, audit_log
```

Key properties, enforced in code and tests:

- **Money is integer micro-USD.** No floats anywhere in the money path.
- **Balanced ledger.** Every transaction's postings sum to zero, every agent balance is
  non-negative, and the wallet cache can be rebuilt from the append-only ledger.
- **Idempotent writes.** Every mutation accepts `Idempotency-Key`; ledger postings are keyed too, so
  a duplicated PayPal webhook cannot double-credit.
- **LLM proposes, code decides.** Agent output is parsed as JSON, validated against a schema and
  clamped by pure rules (price band, caps, allowlist, velocity, approvals). Model text is never
  executed, never used in a query, and never passed between agents — only numbers cross.
- **Humans stay on the loop.** Per-trade and daily caps, approvals above a threshold, an append-only
  audit log, pause/resume per agent and a global kill switch that blocks every state change.

## API (summary)

| Method and path | Purpose | Role |
|---|---|---|
| `POST /api/v1/session/login`, `/judge` | Operator login, metered judge session | none |
| `GET/POST /api/v1/agents`, `PATCH /agents/{id}/policy` | Registry and policy | viewer / operator |
| `POST /api/v1/agents/{id}/pause`, `/resume` | Human control | operator |
| `POST /api/v1/trades`, `GET /trades`, `/trades/{id}/negotiation` | Run and inspect trades | judge / operator, viewer |
| `GET /api/v1/trades/{id}/evidence` | Execution evidence and verification checks | viewer |
| `GET /api/v1/trades/{id}/dispute`, `POST /api/v1/trades/{id}/dispute` | Inspect or open an evidence dispute | viewer / operator |
| `POST /api/v1/trades/{id}/dispute/resolve` | Refund or release held provider funds | operator |
| `GET /api/v1/agents/{id}/reputation` | Evidence-windowed provider reputation | viewer |
| `GET /api/v1/ledger/entries`, `/balances`, `/invariant`, `/netting` | Ledger truth | viewer |
| `POST /api/v1/funding`, `/funding/{id}/capture` | PayPal top-up | operator |
| `POST /api/v1/settlement/run`, `GET /settlement/batches`, `/payouts` | Netting and payouts | operator / viewer |
| `GET/POST /api/v1/approvals`, `/approvals/{id}/decision` | Human approvals | viewer / operator |
| `POST /api/v1/scenarios/{S1..S4}/run` | Guided demos | judge, operator |
| `GET /api/v1/forecasts`, `/reservations`, `POST /reservations` | Forecast capacity | viewer / judge |
| `GET/POST /api/v1/loans` | Credit lines | viewer / judge |
| `POST /api/v1/control/kill-switch`, `/workers/{id}/chaos` | Emergency controls | operator |
| `POST /mcp` | MCP JSON-RPC: initialize, tools/list, tools/call | viewer |
| `GET /api/v1/treasurer/plan`, `/payments/overview` | Treasurer proposal and PayPal read model | viewer |
| `GET /api/v1/hackathon/readiness` | PayPal, workers, receivers, evidence, and ledger readiness | viewer |
| `POST /api/v1/demo/reset` | Wipe trades and reseed demo agents | operator |
| `GET /api/v1/events/stream` | SSE event stream (replayable) | viewer |
| `POST /webhooks/paypal` | PayPal events (signature verified) | signature |
| `GET /healthz`, `/metrics` | Health and metrics | public |

OpenAPI: `/docs`. Postman collection: `postman/aeon.collection.json`.

## Tools used

- **PayPal** — Orders v2 (funding), Payouts v1 (settlement), webhook signature verification,
  reconciliation by webhook plus polling, and an **MCP server** (`POST /mcp`, JSON-RPC 2.0) whose
  treasurer tools read orders, transactions and balances and *propose* a payout batch. The same shape
  is what a PayPal Agent Toolkit host connects to; every tool is read-only or proposing, so no MCP
  client can move money without the guardrail and approval path.
- **Cloudflare Workers AI** — negotiation moves and credit decisions, cached for replay.
- **MongoDB** — double-entry ledger, JSON-schema validators, TTL collections, unique idempotency keys.
- **React + AG Grid + React Flow**, **FastAPI**, **Render** (`render.yaml`).

## Deployment

### Single Render Web Service

For a simple hackathon deployment, one Render Web Service can run the API and both workers as
child processes. Create one Python Web Service with:

```text
Root directory: aeon
Build command: pip install -r backend/requirements.txt && pip install -r worker/requirements.txt
Health check: /healthz
```

Use this start command:

```bash
bash -c "cd worker && WORKER_ID=worker-atlas uvicorn app.main:app --host 127.0.0.1 --port 8001 & cd worker && WORKER_ID=worker-boreal uvicorn app.main:app --host 127.0.0.1 --port 8002 & cd backend && exec uvicorn app.main:app --host 0.0.0.0 --port \$PORT"
```

Set the API's internal worker URLs:

```text
WORKER_URLS=http://127.0.0.1:8001,http://127.0.0.1:8002
```

The shared `HMAC_SHARED_SECRET` is inherited by all three processes. This topology is convenient
for a demo but less resilient: a worker crash restarts the whole service. Render's free plan may
also sleep or restart the combined process.

Set these additional API variables on the same service:

```text
MONGODB_URI=<MongoDB Atlas connection string>
MONGODB_DB=aeon
APP_ENV=production
AUTO_SEED=true
PAYPAL_ENV=sandbox
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=<PayPal sandbox client ID>
PAYPAL_CLIENT_SECRET=<PayPal sandbox client secret>
PAYPAL_WEBHOOK_ID=<PayPal WH-... ID>
SESSION_SECRET=<long random value>
HMAC_SHARED_SECRET=<long random value>
ALLOWED_ORIGIN=https://<your-vercel-domain>
PAYPAL_RETURN_URL=https://<your-vercel-domain>/?funding=return
PAYPAL_CANCEL_URL=https://<your-vercel-domain>/?funding=cancel
LLM_MODE=off
```

Keep PayPal credentials, MongoDB credentials, and random secrets in Render's environment settings,
not in GitHub. Configure Cloudflare later by setting `LLM_MODE=live`, `CF_ACCOUNT_ID`,
`CF_API_TOKEN`, and `CF_MODEL`.

### Separate Render services (recommended)

The more reliable production shape is a Vercel-hosted dashboard, a Render API, two Render worker
services, and MongoDB Atlas. `render.yaml` creates these three Render services automatically:

- `aeon-api`
- `aeon-worker-atlas`
- `aeon-worker-boreal`

In Render, choose **New → Blueprint**, connect this repository, and select `aeon/render.yaml`.
Set all `sync: false` values in the Render dashboard; never commit them. The API's
`WORKER_URLS` must contain the public HTTPS URLs of both workers, and the same
`HMAC_SHARED_SECRET` must be configured on the API and both workers.

The dashboard is deployed separately to Vercel:

```text
Root directory: aeon/dashboard
Build command: npm run build
Output directory: dist
VITE_API_BASE=https://your-api.onrender.com
```

Set the API's `ALLOWED_ORIGIN`, `PAYPAL_RETURN_URL`, and `PAYPAL_CANCEL_URL` to the final Vercel
origin. Create the PayPal sandbox webhook after the API has a public URL:

```text
https://your-api.onrender.com/webhooks/paypal
```

Then set the resulting `WH-...` value as `PAYPAL_WEBHOOK_ID` and redeploy the API.

The ledger is the source of truth, so a worker restart does not lose money state. Docker files and
Docker Compose are intentionally not part of the deployment path.

**[`docs/CREDENTIALS.md`](docs/CREDENTIALS.md)** is the full runbook: every key, where to get it, the
order to set them, and a failure playbook. **[`docs/SUBMISSION.md`](docs/SUBMISSION.md)** holds the
paste-ready write-up, the demo-video shot list and the judge test path.

## Limitations and honest scope

- Single FastAPI process: rate limiting and the SSE fan-out are in-process. Multi-instance deployment
  would need Redis for both.
- Payouts are rounded to cents (PayPal's minimum unit); sub-cent dust stays in the ledger.
- The orchestrated trade runs synchronously on the request (a few seconds); a production system would
  move it to a queue.
- Agent "regions" and the energy price model are simulated; only the weather behind them is real.
- No real funds, no production credential handling, and no claim of production readiness.

## License

MIT — see [LICENSE](LICENSE).
