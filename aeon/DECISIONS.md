# AEON Design Decisions

Blueprint ambiguities resolved during implementation, with the reasoning that matters for review.
Every entry follows: decision → why → impact.

## Money and ledger

**1. `treasury_float` is a negative counter-account.**
Every posting must sum to zero, and the blueprint forbids negative agent balances, so money entering
AEON is booked as `treasury_float` −X / `agent_available` +X. The magnitude of `treasury_float` is
therefore the float actually held at PayPal, and that is what the treasury reserve and payout caps
check (`LedgerService.treasury_funds_micro`). *Impact:* the ledger never shows a positive "cash on
hand" line; the dashboard reports the float as a magnitude.

**2. One transaction header per idempotency key.**
Ledger lines are append-only with per-line `idem_key`, but the replay guard reads a `ledger_txns`
document whose `_id` *is* the idempotency key. A unique index on the per-line key alone would reject
the second line of every double entry. *Impact:* replaying a posting returns the original `txn_id`
and does not move money.

**3. Wallet caches are disposable; `rebuild_wallets` is the repair path.**
MongoDB transactions are not available on the free tier without a replica set, so wallet `$inc`s
follow the ledger insert. If the process dies in between, `POST /api/v1/ledger/rebuild-wallets`
recomputes balances from the append-only ledger and the invariant reports the discrepancy meanwhile.
*Impact:* the ledger, never the cache, is the source of truth.

**4. Escrow and bond are not payable.**
Netting only considers `available` balance. Escrow still backs open trades and bond still backs SLA
obligations. *Impact:* an agent cannot cash out money it owes.

**5. Cash-out is opt-in per agent (`policy.cash_out`).**
Net-positive agents that keep working capital inside AEON would otherwise be paid out on every batch.
Only agents that opt in appear in a settlement. Seed sets it for providers. *Impact:* consumers keep
their balance; providers get paid.

**6. Payouts round to cents.**
PayPal's minimum unit is 0.01, so `micro_to_decimal` rounds half-up. Sub-cent remainder stays in the
ledger rather than being invented or lost. *Impact:* `PAYOUT_MIN_MICRO` defaults to 10 000 µUSD, the
real PayPal floor.

**7. Platform fee is charged from the seller's available balance after release, best-effort.**
A failed fee charge is logged and never blocks settlement; charging it from escrow would make the
buyer pay it. *Impact:* fee revenue can lag by one trade in extreme cases.

## Agents and AI

**8. Only numbers cross between agents.**
Each negotiation move is a JSON object whose `price_micro`/`accept` are validated; `reasoning` is
stored for the transcript and never enters the counterparty's prompt. This kills the cross-agent
prompt-injection path the blueprint warns about. *Impact:* transcripts show reasoning the other side
never saw.

**9. Every LLM call has a deterministic fallback.**
`LLM_MODE=off` or a provider outage must not stop the demo, so buyer/seller moves fall back to a
band-clamped price and credit decisions to a stated rule (approve with a risk premium, refuse after
two late deliveries). Provenance is stored on each transcript row (`live`, `cache`, `replay`,
`fallback`). *Impact:* the UI can always say where a decision came from.

**10. Prices are in cents, not fractions of a cent.**
A job must be able to clear the PayPal payout floor. Base CPU cost is 0.25 USD/CPU-second with a
0.2 s floor, so a small image resize settles around 0.05 USD. *Impact:* demo numbers are meaningful
money, not dust.

## Security and operations

**11. Operator password: hash preferred, dev fallback allowed.**
Production requires `OPERATOR_PASSWORD_HASH` (bcrypt). `OPERATOR_PASSWORD` exists for local demos and
is refused in production by `assert_production_safe()` together with default secrets and
`PAYPAL_ENV=live`. *Impact:* a deployed instance cannot silently run with dev credentials.

**12. Judge mode is unauthenticated but metered.**
Judges get a 30-minute session with 10 scenario runs, tracked in `users_sessions` and decremented
atomically. Judge sessions cannot fund, settle, pause agents or touch the kill switch. *Impact:*
public demo access without giving away write access to money movements.

**13. In-process rate limiting and SSE fan-out.**
One process per the free tier; a Redis dependency would add failure modes without adding value at
this scale. Documented as a limitation for multi-instance deployment.

**14. `memory://` database mode is explicit, never implicit.**
It exists so the project runs without MongoDB installed, and it logs a warning at startup. It is not
a silent fallback from a real connection string. *Impact:* durable demos must use MongoDB.

**15. PayPal failure compensation is explicit.**
Funds move to `payout_in_flight` before the API call, then either complete or reverse. A crash
mid-batch leaves an auditable in-flight position instead of silent loss, and `settlement/batches/{id}/reconcile`
is safe to retry because each item's ledger operations are idempotent.

**16. MCP tools read and propose; they never move money.**
`POST /mcp` speaks JSON-RPC 2.0 and exposes orders, transactions, balances and a
`aeon_propose_payout_batch` tool. The proposal is a recommendation that lands in the normal
approval + guardrail path; no tool can call PayPal Payouts directly. *Impact:* an MCP host (a PayPal
Agent Toolkit client, a chat assistant, a judge's own script) can inspect the treasury and get a
justified batch proposal without becoming a privileged money mover. Only listing and proposing are
exposed, so a leaked tool surface cannot drain the treasury.

**17. Demo reset clears idempotency keys too.**
The reset endpoint empties the ledger, trades, approvals and `idempotency_keys` together. Without the
last one a reseed replays the original funding request IDs, the server correctly answers "already
processed", and the demo comes back with empty wallets. *Impact:* the reset button is genuinely
repeatable, which is what a live judge run needs.

**18. Post-deployment checks are a script, not a checklist.**
`scripts/smoke.py` exercises S1-S3, an MCP tool call, funding order plus capture, settlement and the
ledger invariant against any base URL, and reports which adapters are still simulated. *Impact:* after
credentials are added the verification is one command with a real exit code, and any regression shows
up as a named failed check instead of a vague "looks fine".

## Deferred deliberately

- The natural-language operator command bar, PayPal Invoicing and the Bryntum timeline are
  stretch goals and are not implemented.
- Trades run synchronously on the request; a queue is the obvious next step.
- APIMatic SDK generation and Playwright browser tests are left for the polish window;
  `scripts/smoke.py` covers the API-level end-to-end path instead.
