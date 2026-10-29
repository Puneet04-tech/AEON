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

## What is real and what is simulated

| Element | Status | Detail |
|---|---|---|
| PayPal Orders, Payouts, webhooks | **Real (sandbox)** | Actual API calls, statuses and `verify-webhook-signature` |
| Agent decisions (offers, credit) | **Real** | Cloudflare Workers AI, JSON-validated, clamped by guardrails |
| Compute jobs | **Real** | Image resize (Pillow) and matrix multiply (numpy) on separate workers, CPU metered with `process_time` |
| Ledger, escrow, netting, bonds, loans | **Real** | MongoDB double-entry ledger with invariants and idempotency |
| Weather input | **Real** | Open-Meteo current forecast, no API key |
| Energy price factor and "regions" | **Simulated** | Deterministic model over real temperature; labelled in the UI |
| Worker outage | **Simulated trigger, real handling** | Signed chaos switch → real health failure, reroute, penalty |
| Money | **Sandbox** | Stated in the console footer, `/api/v1/config` and this README |

If no PayPal credentials are present, the API falls back to a **simulated PayPal adapter**
(`PAYPAL_MODE=mock`) that never contacts PayPal. The console labels it `PAYPAL MOCK (SIMULATED)`.
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

### Docker Compose (MongoDB + API + two workers + console)

```bash
cp .env.example .env          # optional: add PayPal sandbox + Cloudflare credentials
docker compose up --build
open http://localhost:5173    # operator password defaults to demo-operator
```

### Local, no database install

```bash
cd backend
pip install -r requirements.txt
MONGODB_URI=memory:// OPERATOR_PASSWORD=demo-operator LLM_MODE=off uvicorn app.main:app --port 8000

cd ../worker
pip install -r requirements.txt
WORKER_ID=worker-atlas WORKER_PORT=8001 uvicorn app.main:app --port 8001
WORKER_ID=worker-boreal WORKER_PORT=8002 uvicorn app.main:app --port 8002

cd ../dashboard
npm install && npm run dev    # http://localhost:5173, proxies /api to :8000
```

`MONGODB_URI=memory://` is an explicit local demo mode: process-local, wiped on restart.

### Tests

```bash
cd backend && python -m pytest -q     # 58 tests
cd worker  && python -m pytest -q     # 11 tests
cd dashboard && npx tsc --noEmit && npm run build
```

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
| `GET /api/v1/ledger/entries`, `/balances`, `/invariant`, `/netting` | Ledger truth | viewer |
| `POST /api/v1/funding`, `/funding/{id}/capture` | PayPal top-up | operator |
| `POST /api/v1/settlement/run`, `GET /settlement/batches`, `/payouts` | Netting and payouts | operator / viewer |
| `GET/POST /api/v1/approvals`, `/approvals/{id}/decision` | Human approvals | viewer / operator |
| `POST /api/v1/scenarios/{S1..S4}/run` | Guided demos | judge, operator |
| `GET /api/v1/forecasts`, `/reservations`, `POST /reservations` | Forecast capacity | viewer / judge |
| `GET/POST /api/v1/loans` | Credit lines | viewer / judge |
| `POST /api/v1/control/kill-switch`, `/workers/{id}/chaos` | Emergency controls | operator |
| `GET /api/v1/events/stream` | SSE event stream (replayable) | viewer |
| `POST /webhooks/paypal` | PayPal events (signature verified) | signature |
| `GET /healthz`, `/metrics` | Health and metrics | public |

OpenAPI: `/docs`. Postman collection: `postman/aeon.collection.json`.

## Tools used

- **PayPal** — Orders v2 (funding), Payouts v1 (settlement), webhook signature verification,
  reconciliation by webhook plus polling, Agent Toolkit/MCP reading as the documented optional path.
- **Cloudflare Workers AI** — negotiation moves and credit decisions, cached for replay.
- **MongoDB** — double-entry ledger, JSON-schema validators, TTL collections, unique idempotency keys.
- **React + AG Grid + React Flow**, **FastAPI**, **Render** (`render.yaml`).

## Deployment

`render.yaml` defines the API and two workers; add the secrets in the Render dashboard. The ledger is
the source of truth, so a worker restart never loses money state. `docker compose up` runs the whole
stack locally.

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
