# AEON — submission kit

Two things live here: a paste-ready Devpost write-up and a shot-by-shot script for the demo video.
Replace `<<...>>` placeholders with your links before submitting.

---

## Part 1 — Devpost write-up

**Project name:** AEON — the clearing house for agent-to-agent work

**Tagline:** Five AI agents negotiate, do real compute work, and settle it in money — with a
double-entry ledger, deterministic guardrails, and PayPal payouts underneath.

**Elevator pitch (one paragraph, for the top of the page):**

> Autonomous agents are starting to buy work from each other, and nobody has built the boring part:
> the books. AEON is a clearing house where a buyer agent negotiates a price with a provider agent,
> escrows funds, the provider actually runs the job on a real worker with metered CPU, and the money
> settles through a double-entry ledger — with penalties for breaches, credit lines when a provider
> fails, net settlement instead of thousands of micro-payments, and PayPal Orders in and PayPal Payouts
> out. The LLM proposes; deterministic code disposes. Every number on screen can be traced to a ledger
> entry.

### Inspiration

Multi-agent demos usually end at "the agents talked to each other". The moment agents transact, you
need what every market has needed: escrow, an append-only ledger, limits a model cannot talk its way
past, and a way to pay out without paying a fee per micro-transaction. Agentic commerce is arriving
faster than its accounting is, so we built the accounting.

### What it does

- **Negotiation with a hard floor.** A buyer agent and a provider agent negotiate in up to three
  rounds. An LLM proposes each price; a deterministic guardrail (price band, per-trade cap, daily cap,
  allowlist, velocity, treasury reserve, approval threshold, kill switch) decides whether it may exist.
  The console shows both the proposal and the verdict.
- **Real work, really metered.** The winning job is dispatched over signed HMAC with a nonce to a
  separate worker service, which runs actual Pillow image resizes and numpy matrix products and
  reports CPU seconds from `process_time`. The buyer re-derives the result digest before releasing
  escrow.
- **A ledger, not a balance field.** Every movement is a balanced transaction in integer micro-USD
  across agent wallets, escrow, bond, treasury float and fee accounts. Wallets are rebuildable caches;
  the invariant `sum(all entries) = 0` is checked live and shown in the UI.
- **Failure has a price.** When a provider breaches its SLA, a penalty is charged from its performance
  bond, the trade is rerouted to another provider, and if the buyer is short of cash a credit line from
  the lender agent funds it — all as ledger entries.
- **Net settlement, then PayPal.** Instead of paying per trade, positions are netted into a batch.
  Above an approval threshold it waits for a human. Then it goes out as a PayPal Payouts batch from the
  sandbox business float to the agents' receivers, reconciled item by item.
- **Funding in.** PayPal Orders v2 creates a real sandbox order, capture is verified against the
  requested amount, and credits are idempotent by capture id, so a replayed webhook cannot mint money.
- **Agent-native surface.** An MCP server (`POST /mcp`) exposes orders, transactions, balances and a
  `propose_payout_batch` tool, so an external agent host can inspect the treasury and get a justified
  batch proposal — without ever gaining the ability to move money.
- **Operations.** Kill switch, per-agent pause, approval queue, audit log, judge mode with metered
  quotas, and a reset endpoint for repeatable demos.

### How we built it

Python 3.11 + FastAPI services, MongoDB as the system of record, a React/Vite console (React Flow for
the agent topology, AG Grid for the data planes, SSE for live events), and Render/Vercel for hosting.

The design rule that shaped everything: **the model is an advisor, never an authority.** The LLM
produces a price or a recommendation; policy code re-checks it against integer micro-USD limits and
either accepts or records why it refused. If the model is unavailable, a deterministic fallback runs
and the transcript says which one produced the number.

Money is integer micro-USD everywhere (1 USD = 1,000,000), so no float ever touches a balance.
Transfers are one ledger transaction with balanced legs, and every mutation takes an idempotency key.

### Challenges we ran into

- **Micro-payments are unshippable one by one.** A $0.056 job cannot justify a per-transfer fee, so we
  had to build netting as a first-class concept, with approval thresholds and per-item reconciliation
  rather than a single payout call.
- **Failure compensation.** A payout batch can die halfway through. We move funds to
  `payout_in_flight` before the API call, then complete or reverse explicitly, so a crash leaves an
  auditable in-flight position instead of a hole.
- **Proving the books.** Tests read the ledger both ways: Hypothesis property tests generate random
  transaction sequences and assert zero-sum, and the live endpoint recomputes the invariant on every
  poll. A demo bug (reset cleared entries but not idempotency keys, so reseeded funding posts were
  correctly rejected as duplicates) was only visible because the invariant and wallets disagreed.
- **Trusting webhooks.** Signature verification plus idempotent crediting by capture id, with an
  explicit 400 on a forged body, so a public endpoint is not a money printer.
- **Keeping the demo honest.** PayPal is sandbox-only and disabled until credentials are configured;
  the runtime labels the active PayPal and AI integration modes.

### Accomplishments we are proud of

- 87 backend tests and 11 worker tests, including randomized ledger invariants and every guardrail rule.
- A rerouting scenario that really fails a worker (signed chaos switch), charges a bond penalty,
  reroutes, and closes the trade with the books balanced.
- Net settlement that ends in real PayPal Payouts items with item-level status.
- A console where a judge can watch the money move: agent graph, ledger, balances, wallet drift,
  approvals, payouts, audit, and a live event drawer.

### What we learned

- Guardrails are a product surface, not a library: showing *why* a price was refused is what makes an
  autonomous agent trustworthy.
- Settlement, not payment, is the hard part of agentic commerce.
- An MCP surface with read-only tools plus "propose" is the right boundary — you can integrate an agent
  host without handing it the treasury.

### What's next

- A queue for job dispatch instead of synchronous trades, and multi-instance SSE via a shared bus.
- Real price feeds (the current energy/region inputs are simulated; weather is live from Open-Meteo).
- A PayPal Agent Toolkit host in the console, so the treasurer recommendation can be driven by an
  operator's own agent.
- Postgres/SQL ledger store for a hardened deployment, plus paid-tier hosting to remove cold starts.

### Links and built-with

- **Live demo:** <<https://aeon-console.onrender.com — operator password: your chosen demo password>>
- **Judge mode:** the "Enter judge mode" button on the login screen (no password, 30 minutes, 10 scenarios)
- **Repository:** <<https://github.com/<you>/aeon-clearing-house>> (MIT)
- **Video:** <<https://youtu.be/...>>

**Built with:** python, fastapi, mongodb, atlas, react, typescript, vite, react-flow, ag-grid,
server-sent-events, render, vercel, paypal-orders-v2, paypal-payouts-v1, paypal-webhooks,
cloudflare-workers-ai, mcp, json-rpc, hypothesis, pytest, pydantic, structlog, pillow, numpy.

---

## Part 2 — Demo video (target 3:00, hard cap whatever Devpost states)

Record at 1440p, browser zoom 100%, no other tabs. Pre-flight: demo reset so wallets are funded,
console logged in, terminals already running, and one trade already executed so the ledger is not
empty at the start.

| Time | On screen | Say (roughly) |
|---|---|---|
| 0:00–0:12 | Title card: "AEON — the clearing house for agent-to-agent work" | "Agents are starting to hire each other. Nobody built the books. So we did." |
| 0:12–0:30 | Coordinator console, agent topology animating | "Five agents: two buyers, two providers, a treasurer and a lender. Contractors negotiate, compute, and get paid on this ledger." |
| 0:30–0:55 | Action bar → **Run trade** (consumer → provider, image resize) | "The buyer and seller negotiate three rounds. The model proposes a price — the guardrail decides whether it is allowed. Escrow is locked before work starts." |
| 0:55–1:15 | Event drawer filling, trade row settling, metering cell | "That job really ran on a separate worker. CPU seconds are metered, the buyer re-derives the digest, and settlement releases escrow to the seller." |
| 1:15–1:30 | Ledger tab, invariant chip, balances | "Every movement is a balanced, append-only entry. The invariant is recomputed live: the books sum to zero, always." |
| 1:30–1:52 | Scenario **S2**: chaos switch on, trade fails, penalty, reroute | "Now a real failure. The provider breaches its SLA: bond penalty, reroute to the other provider, and a credit line when the buyer is short. All ledger entries, no exceptions in the console." |
| 1:52–2:15 | Action bar → pick agent, amount `5`, **Fund** → order created and captured | "Funding is a real PayPal sandbox order and capture. The amount is verified before we credit, and a replayed webhook cannot double-credit." |
| 2:15–2:40 | **Settle** → net batch → approval in **Approvals** tab → payout items succeed in **Payouts** | "We do not pay per trade — we net. Above the threshold it waits for a human. Then it leaves as a PayPal Payouts batch, reconciled item by item." |
| 2:40–3:00 | **Audit** tab, MCP tool list, close on invariant + config labels | "Every action is audited, an MCP endpoint lets another agent inspect the treasury without moving money, and everything simulated is labelled. Model proposes, code disposes, the ledger proves it." |

**Rules that keep the video honest:** say "sandbox" whenever PayPal appears; do not claim AI decided
anything the guardrail rejected; show the invariant rather than asserting it.

---

## Part 3 — Judge test path (put this in the write-up too)

1. Open the console → **Enter judge mode** (no password).
2. Action bar → **Run trade** → the trade appears in **Trades** and settles on its own.
3. **Ledger** tab → invariant `0`, balances match the trade.
4. Scenario chips → S2 (failure + reroute), S3 (weather-priced reservation).
5. Operator login → action bar **Fund** (pick an agent, amount `5`) → sandbox order captured.
6. **Settle** → batch is created → approve in **Approvals** if asked → **Payouts** shows `SUCCEEDED`.
7. **Audit** shows the whole story in order.

---

## Before you hit submit

- [ ] Public repo, MIT licence visible, CI green.
- [ ] `.env` is **not** committed (`git status` clean of it).
- [ ] Deployed API `/healthz` → `mongo: true`; `/api/v1/config` → `paypal_mode: sandbox`, `llm_mode: live`.
- [ ] Seed `paypal_email` values replaced with your own sandbox receivers, then a real payout verified.
- [ ] Webhook created for the deployed URL; `PAYPAL_WEBHOOK_ID` set; a forged body returns 400.
- [ ] `python scripts/smoke.py --base-url ...` exits 0.
- [ ] Keep-warm pinger or paid instance for the judging window.
- [ ] Demo reset run before recording; video uploaded and linked; write-up placeholders replaced.
