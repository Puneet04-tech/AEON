# AEON — credentials and deployment runbook

Everything below is what *you* have to do, in order. Each step says what it unlocks, the exact
variable name the code reads, and what to check afterwards. Nothing here needs to be shared in chat:
put the values in `aeon/.env` locally and in the Render dashboard for the deployment.

Read section 0 first: it is the honest split between what is already real and what a credential
changes.

---

## 0. What is simulated today vs. what a key makes real

| Capability | Without credentials | With credentials |
|---|---|---|
| Money movement (funding) | `mock` adapter: order created and captured in-process, clearly labelled in the UI and `/api/v1/config` | Real sandbox order + real `/v2/checkout/orders/{id}/capture`, amount verified before credit |
| Webhooks | Endpoint exists; a forged body is rejected by signature check | Real `verify-webhook-signature` round trip with PayPal |
| Settlement payouts | `mock` items go straight to `SUCCEEDED` | Real Payouts batch from your sandbox business account, per-item reconciliation |
| Negotiation reasoning | Deterministic fallback (no network) | Live Workers AI call; the LLM proposes, code decides |
| Persistence | `memory://` wipes on restart | Atlas: ledger survives restarts and redeploys |
| Compute jobs / metering | **Already real** — signed dispatch to real workers, real Pillow/numpy work, real `process_time` | unchanged |
| Ledger, guardrails, approvals, SSE | **Already real** | unchanged |

So: four credentials flip four simulated paths. Nothing else about the demo is faked.

---

## 1. MongoDB Atlas — `MONGODB_URI`, `MONGODB_DB`

**Unlocks:** durable ledger, trades, approvals, sessions across restarts and deploys.

1. Sign in at <https://cloud.mongodb.com> → **Create** a project → **Build a Database** → choose
   **M0 Free**.
2. **Database Access** → *Add New Database User* → username + generated password. Role:
   *Read and write to any database*. Save the password now.
3. **Network Access** → *Add IP Address* → `0.0.0.0/0` (Render's free tier has no fixed egress IPs;
   this is a demo database with sandbox money, so wide access is acceptable — say so in the write-up).
4. **Clusters → Connect → Drivers** → copy the `mongodb+srv://...` string and substitute the user
   password. Append the database name:

```
MONGODB_URI=mongodb+srv://aeon_user:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=aeon
```

**Check:** start the API, then `curl localhost:8000/healthz` — it must return `"mongo": true`
(`false` means the URI, password encoding or IP allowlist is wrong). The boot log must not say
`memory:// mode`. Indexes and JSON-schema validators are applied on startup, and the five demo agents
seed only when the database is empty.

> Escape hint: if the password contains `@ : / ?`, percent-encode it (`@` → `%40`).

---

## 2. PayPal sandbox — `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_WEBHOOK_ID`

**Unlocks:** real Orders v2 funding, real Payouts settlement, verified webhooks.

### 2a. App credentials

1. <https://developer.paypal.com/dashboard/applications/sandbox> → **Create App** (type *Merchant*).
2. Copy **Client ID** and **Secret** (sandbox, not live):

```
PAYPAL_CLIENT_ID=...
PAYPAL_CLIENT_SECRET=...
PAYPAL_ENV=sandbox
PAYPAL_MODE=sandbox
PAYPAL_CURRENCY=USD
```

`PAYPAL_ENV=live` is refused by `assert_production_safe()` — this project only ever moves sandbox
money.

### 2b. Receiver accounts (needed for Payouts)

1. <https://developer.paypal.com/dashboard/accounts> → you get a **Business** sandbox account and
   several **Personal** ones by default. Create three Personal accounts if you have fewer.
2. Log into each Personal account (the dashboard has a "Log in" link with generated credentials) and
   **confirm the email** if prompted — Payouts to unconfirmed sandbox emails fail with
   `RECEIVER_UNREGISTERED`.
3. The treasury float is the **Business** account: funding captures land there, payouts leave from
   there. Keep its balance healthy: **Log in → Add funds** (sandbox) if a payout is rejected for
   insufficient funds.
4. The seeded agents currently carry placeholder receivers (`atlas-buyer@example.com` and friends,
   `backend/app/db/seed.py`). **For a judged live payout, replace those five addresses with your
   sandbox Personal account emails before the final deploy** — otherwise real Payouts items fail with
   `RECEIVER_UNREGISTERED` and only the in-process path is demonstrated. The console's *Payments*
   grid shows the receiver on every row so you can confirm what is configured.

### 2c. Webhook (create *after* the API is deployed — it needs a public URL)

1. App details → **Webhooks** → **Add Webhook**.
2. URL: `https://<your-api-host>/webhooks/paypal`
3. Event types — either tick **All events**, or exactly these (what the handler understands):
   - *Checkout order approved* → `CHECKOUT.ORDER.APPROVED`
   - *Checkout order completed* → `CHECKOUT.ORDER.COMPLETED`
   - *Payment capture completed* → `PAYMENT.CAPTURE.COMPLETED`
   - *Payouts item succeeded / denied / failed / returned / blocked* → `PAYOUTS-ITEM.*`
4. Copy the generated **Webhook ID** (starts with `WH-`):

```
PAYPAL_WEBHOOK_ID=WH-...
```

**Check:** `POST /webhooks/paypal` with a garbage body must return **400** (signature rejected);
a real capture in the console must produce a `webhook.processed` row in the *Audit* / event drawer and
must not double-credit the wallet (idempotent by capture id).

---

## 3. Cloudflare Workers AI — `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `CF_MODEL`

**Unlocks:** live LLM proposals in negotiation and in the treasurer plan.

1. <https://dash.cloudflare.com> → **Workers & Pages** → the **Account ID** is in the right-hand
   sidebar (also on the Workers overview page). Enable **Workers AI** once if prompted.
2. <https://dash.cloudflare.com/profile/api-tokens> → **Create Token** → *Custom token*:
   - Permissions: **Account → Workers AI → Read**
   - Account resources: your account
3. Set:

```
CF_ACCOUNT_ID=...
CF_API_TOKEN=...
CF_MODEL=@cf/meta/llama-3.1-8b-instruct
LLM_PROVIDERS=cloudflare
LLM_MODE=live
```

**Check:** `GET /api/v1/config` should report `llm_mode: live`; a trade's negotiation transcript must
show `source: llm` for at least one round. If the model is unavailable the code falls back
deterministically — that is by design, and the transcript says which happened. `LLM_MODE=replay`
uses the cached responses (`.llm_cache.json`) with no network, `LLM_MODE=off` is deterministic only.

---

## 4. Secrets you generate yourself

| Variable | How | Notes |
|---|---|---|
| `SESSION_SECRET` | `python -c "import secrets;print(secrets.token_urlsafe(48))"` | Signs session tokens |
| `HMAC_SHARED_SECRET` | same command | **Must be byte-identical on the API and both workers**, or every job is rejected as forged |
| `OPERATOR_PASSWORD_HASH` | see below | bcrypt; `OPERATOR_PASSWORD` plaintext is refused once `APP_ENV=production` |
| `APP_ENV` | `production` | Turns on the production safety checks |
| `ALLOWED_ORIGIN` | e.g. `https://aeon-console.onrender.com` | CORS for the console |
| `WORKER_URLS` | comma-separated worker base URLs | No trailing slash |

Generate the operator hash locally (never paste the password anywhere else):

```bash
cd aeon/backend && python -c "
import bcrypt, getpass
p = getpass.getpass('operator password: ')
print(bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode())
"
```

Paste the `$2b$...` string as `OPERATOR_PASSWORD_HASH`. Quote it in `.env` (`OPERATOR_PASSWORD_HASH='$2b$...'`)
so the `$` is not expanded.

Limits you may want to tune for a demo (all micro-USD, `1 USD = 1_000_000`):
`TREASURY_RESERVE_MICRO` (default 20 USD), `APPROVAL_THRESHOLD_MICRO` (25 USD),
`PAYOUT_MIN_MICRO`, `FUNDING_MAX_MICRO` (50 USD), `MAX_TRADE_MICRO` (5 USD).

---

## 5. GitHub repository

Judges require a public repo. From `F:/AEON`:

```bash
gh auth status                      # must be logged in
gh repo create aeon-clearing-house --public --source=. --remote=origin --push
```

Then confirm the MIT `LICENSE` is at the repo root (it is), the README renders, and the **Actions**
tab is green (CI runs backend + worker tests and a dashboard build).

---

## 6. Deploy (Render blueprint, ~10 minutes)

1. <https://dashboard.render.com/blueprints> → **New Blueprint Instance** → pick the repo.
   `render.yaml` creates four services: `aeon-api`, `aeon-console`, `aeon-worker-atlas`,
   `aeon-worker-boreal`.
2. Set the `sync: false` secrets on **each** service when prompted:
   - `aeon-api`: `MONGODB_URI`, `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_WEBHOOK_ID`,
     `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `HMAC_SHARED_SECRET`, `OPERATOR_PASSWORD_HASH`
   - both workers: the **same** `HMAC_SHARED_SECRET`
3. If your service names differ from the blueprint, update `WORKER_URLS` on the API and
   `VITE_API_BASE` on the console, then redeploy.
4. Verify in this order:
   - `https://<api>/healthz` → 200, database connected, `paypal_mode: sandbox`
   - `https://<console>/` → login screen renders, operator login works
   - Workers: `GET /health` on each, and `/api/v1/workers/health` from the API shows both reachable
5. Now do **2c** (create the webhook) and set `PAYPAL_WEBHOOK_ID`, then redeploy the API.
6. Free instances sleep after ~15 minutes idle. For the judging window either upgrade to Starter for
   the week or point a free uptime pinger at `/healthz` every 5 minutes.

**Render + Atlas gotcha:** a `ServerSelectionTimeoutError` in the API log means Network Access is
still restricted — re-check section 1, step 3.

---

## 7. Verify the real paths with one command

```bash
cd aeon && python scripts/smoke.py \
  --base-url https://aeon-api.onrender.com \
  --password "<operator password>"
```

It runs S1–S3, calls an MCP tool, creates and captures a funding order, settles a batch, checks the
ledger invariant, and prints which adapters are still simulated. Exit code 0 means every check passed;
a failure names the exact check, so you know which section above to revisit.

Manual spot checks worth doing once (they are what a judge will poke):
- Judge mode: *Try as judge* → run a scenario → quota decrements, and funding/settlement buttons are
  refused.
- Kill switch on → new trade rejected with a clear reason; off → works again.
- Approvals: a settlement above `APPROVAL_THRESHOLD_MICRO` waits for operator approval.
- Demo reset (`POST /api/v1/demo/reset`) → wallets funded again, trades cleared.

---

## 8. Failure playbook

| Symptom | Cause | Fix |
|---|---|---|
| `paypal_mode: mock` in `/api/v1/config` after setting keys | Keys empty/whitespace or `PAYPAL_MODE=mock` | Re-check the two PayPal vars; `PAYPAL_MODE=sandbox` |
| Funding returns `401 invalid_client` | Using live keys, or a space/newline in the secret | Regenerate the sandbox secret, paste exactly |
| Webhook returns 400 with a valid PayPal event | `PAYPAL_WEBHOOK_ID` from another app/webhook | Recreate the webhook for this URL and update the ID |
| Payout item `RECEIVER_UNREGISTERED` | Sandbox receiver email not confirmed | Log into that sandbox account once and confirm |
| Payout item `INSUFFICIENT_FUNDS` | Business sandbox balance too low | Add sandbox funds to the Business account |
| Trade fails with `invalid signature` | `HMAC_SHARED_SECRET` differs between API and worker | Set the identical value on all three services |
| `Refusing to run production with default secrets` | `APP_ENV=production` with `dev-*` secrets | Set real `SESSION_SECRET` and `HMAC_SHARED_SECRET` |
| First request after idle takes 30s+ | Free tier spin-down | Keep-warm pinger or paid instance |
