# AEON hackathon submission guide

## One-line pitch

**AEON is the trust and settlement layer for autonomous agent commerce: AI
agents negotiate work, PayPal sandbox controls the money, software workers
produce evidence, and AEON verifies, disputes, and settles the result.**

## What judges should see

1. Enter judge mode or sign in as an operator.
2. Confirm both software workers are healthy.
3. Run a compute trade.
4. Show AI negotiation provenance (`live`, `replay`, or deterministic fallback)
   and the guardrail decision.
5. Show PayPal as `SANDBOX` after sandbox credentials are configured.
6. Show the trade progress through escrow, dispatch, evidence, independent
   verification, and settlement.
7. Select the trade and show worker identity, input/output digests, runtime,
   CPU time, and verification checks.
8. Enable the software corruption demonstration on a worker, run another trade,
   and show checksum rejection and rerouting/refund.
9. Open a dispute on a settled trade and show the dedicated ledger hold,
   followed by refund or release.

The Cloudflare Workers AI credentials are intentionally supplied at deployment
time, not committed to the repository. Set `LLM_MODE=live`, `CF_ACCOUNT_ID`,
`CF_API_TOKEN`, and `CF_MODEL` in the API environment to show live AI
negotiation. `LLM_MODE=replay` is useful for a deterministic recording without
spending live model limits.

## PayPal requirement

AEON is sandbox-only and does not simulate money movement in the product. Set
these Render environment variables before demonstrating funding or payouts:

```text
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=<PayPal sandbox client id>
PAYPAL_CLIENT_SECRET=<PayPal sandbox client secret>
PAYPAL_WEBHOOK_ID=<optional sandbox webhook id>
PAYPAL_RETURN_URL=<Vercel dashboard URL>?funding=return
PAYPAL_CANCEL_URL=<Vercel dashboard URL>?funding=cancel
```

Without those values, the dashboard clearly shows **PAYPAL NOT CONFIGURED** and
disables funding and settlement actions. Compute trades and evidence inspection
remain available because they do not move money through PayPal.

The dashboard also shows a **DEMO READY** indicator. It turns green only after
the API sees healthy workers, a valid ledger invariant, PayPal sandbox
configuration, real provider receiver emails, a configured webhook ID, and at
least one evidence-backed trade. The underlying diagnostic is available at
`GET /api/v1/hackathon/readiness`.

## What the repository handles vs. what the submitter must do

The repository provides the readiness check, PayPal integration, worker
evidence, verification, corruption demonstration, dispute accounting, and
dashboard presentation. Before submission, the owner must still deploy the
services, create the PayPal sandbox webhook, set its webhook ID, replace seeded
`example.com` provider emails with PayPal sandbox receiver accounts, run a
funding/capture and payout test, and record the final video.

## Suggested under-three-minute demo

- 0:00–0:20: state the problem: agents can transact, but buyers cannot easily
  prove that paid work was correct.
- 0:20–0:55: run a normal trade and show AI negotiation, policy guardrails,
  PayPal sandbox escrow, and worker execution.
- 0:55–1:25: open evidence and verification details.
- 1:25–1:55: corrupt a software worker result and show automatic rejection.
- 1:55–2:25: open a dispute, show held funds, then refund or release.
- 2:25–2:50: show provider reputation and explain why AEON is more than an
  agent directory or payment API.

## Submission claims

Do claim:

- PayPal sandbox is the payment rail.
- Cloudflare Workers AI proposes negotiation decisions.
- Deterministic guardrails remain authoritative.
- Software workers produce portable evidence.
- Independent software verification detects disagreement.
- Double-entry accounting and disputes protect settlement.

Do not claim:

- Hardware attestation.
- Production real-money payments.
- Fully autonomous legal dispute decisions.
- That AEON invented agent marketplaces or machine payments.
