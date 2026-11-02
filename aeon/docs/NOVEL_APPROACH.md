# AEON Novel Approach Proposal

## Status

**Approved MVP implemented in the current branch.** The broader roadmap below
still contains future work such as independent second-worker verification and
attestation.

## Executive summary

AEON should not compete as another general-purpose AI-agent directory or
payment protocol. Those categories already have strong projects:

- Fetch.ai Agentverse focuses on hosting, discovering, and connecting agents.
- SingularityNET provides an AI-service marketplace with service payments and
  payment channels.
- Akash provides a decentralized compute marketplace with provider attributes,
  leases, escrow, and provider verification concepts.
- Coinbase x402 provides a standard for machine-to-machine payments over HTTP.

The strongest open opportunity for AEON is the layer between **“an agent was
found”** and **“the buyer should trust the result and release payment.”**

### Proposed product

> **AEON Proof-Carrying Agent Commerce** is a trust and settlement layer for
> agent-to-agent work. Every transaction carries a machine-readable policy,
> execution evidence, result verification, provider reputation impact, and a
> dispute path before final settlement.

In simple language:

> AEON should not only help agents find and pay each other. It should help them
> prove that the promised work was done correctly, decide what happens when it
> was not, and learn which providers can be trusted next time.

## Why this is a real gap

The market is developing several useful layers, but they are usually separated:

| Existing layer | What it solves | What remains for AEON |
|---|---|---|
| Agent directories and registries | Find agents and endpoints | Prove that a particular transaction was safe and successful |
| AI-service marketplaces | Publish and buy services | Standardize work evidence, disputes, and accounting across services |
| Decentralized compute markets | Match workloads with providers | Verify application-level output, not only capacity or lease state |
| Payment protocols | Transfer or authorize money | Decide whether the paid work deserves final settlement |
| Agent frameworks | Coordinate agent messages | Enforce financial policy and preserve an audit-grade transaction record |

This is a product hypothesis, not a claim that no one has attempted any part
of it. Existing systems contain related features. AEON's opportunity is to make
the complete **policy → evidence → verification → dispute → settlement** loop
the primary product rather than treating those concerns as optional add-ons.

## Evidence from existing systems

### Fetch.ai Agentverse

Fetch.ai describes Agentverse as a platform for launching, hosting, managing,
and discovering agents. Its documentation also describes registry-based
discovery and agent communication.

Relevant links:

- [Agentverse](https://www.fetch.ai/agentverse)
- [Fetch.ai Agentverse resources](https://innovationlab.fetch.ai/resources/docs/agentverse/)

**AEON implication:** discovery is becoming available. AEON should focus on
what happens after discovery: transaction controls, evidence, and settlement.

### SingularityNET

SingularityNET provides an AI services marketplace. Its developer materials
describe service payments, payment channels, and escrow-like mechanisms.

Relevant links:

- [SingularityNET marketplace](https://marketplace.singularity.io/)
- [SingularityNET developer portal](https://dev.singularitynet.io/docs/)
- [Multi-Party Escrow overview](https://dev.singularitynet.io/docs/mpe-overview/)

**AEON implication:** marketplace payment and service consumption are not new.
AEON should differentiate with transaction-level execution evidence, policy
decisions, and operational dispute handling.

### Akash

Akash provides decentralized compute and describes provider attributes,
audited-provider selection, leases, bids, escrow, and workload operations.

Relevant link:

- [Akash providers and leases](https://akash.network/docs/learn/core-concepts/providers-leases/)

**AEON implication:** provider selection, pricing, escrow, and compute
marketplaces already exist. AEON should verify the correctness of a specific
job result and make that evidence useful to future provider selection.

### Coinbase x402

Coinbase documents x402 as a way for agents and applications to pay for APIs
and digital services over HTTP.

Relevant links:

- [x402 overview](https://docs.cdp.coinbase.com/x402/welcome)
- [Pay with x402](https://docs.cdp.coinbase.com/payments/payment-acceptance/pay-with-x402)

**AEON implication:** payment transport is increasingly standardized. AEON
should be payment-rail agnostic and own the decision of whether work is
accepted, disputed, or settled.

## The proposed differentiation

### 1. A transaction evidence envelope

Every job should produce a portable evidence record, not only a result payload.

The evidence envelope should include:

- Transaction and job identifiers
- Buyer, provider, and policy versions
- Input digest
- Requested capability and resource limits
- Worker identity
- Worker software/runtime version
- Start and completion timestamps
- Resource metering
- Output digest
- Signature and nonce information
- Verification checks performed
- Evidence confidence level
- Any warnings or deviations

The envelope must not contain secrets or unnecessary user data.

### 2. Three verification levels

AEON should make trust explicit instead of presenting every result as equally
reliable:

#### Level 1: Signed execution evidence

The registered worker signs the job result and reports metering. This is the
level AEON already approaches with HMAC signing and checksums.

#### Level 2: Independent deterministic verification

A second worker or verifier reruns a deterministic job, compares output
digests, and records agreement or disagreement.

#### Level 3: Attested or externally verifiable execution

For selected workloads, AEON can integrate a stronger proof source such as a
trusted execution environment, reproducible container digest, or domain-specific
proof. This should be optional because it increases cost and complexity.

The dashboard should display the verification level next to the trade state.

### 3. Policy-as-contract

Before a job starts, the buyer should approve a machine-readable policy:

- Maximum price
- Maximum duration
- Allowed providers
- Minimum verification level
- Required region or compliance attributes
- Maximum retries
- Automatic refund rules
- Whether human approval is required

The current AEON guardrails are a strong starting point. The novel direction is
to persist the exact policy version used for the transaction and evaluate the
final evidence against that same policy.

## Implemented MVP surfaces

The approved first slice now includes:

- Worker evidence envelopes with input/output digests, runtime version,
  timestamps, CPU metering, and wall time.
- Consumer-side checksum verification persisted with every delivered trade.
- Independent deterministic verification by a second configured software
  worker, with a signed-execution fallback when no verifier is available.
- Evidence and verification APIs at
  `GET /api/v1/trades/{trade_id}/evidence`.
- Evidence-backed dispute creation and operator resolution using a dedicated
  double-entry `agent_dispute_hold` account:
  `POST /api/v1/trades/{trade_id}/dispute` and
  `POST /api/v1/trades/{trade_id}/dispute/resolve`.
- Evidence-windowed provider reputation at
  `GET /api/v1/agents/{agent_id}/reputation`.
- Trade-level provider selection explanations and dashboard display.
- Software-only corrupted-result demonstration through the operator worker
  chaos control (`corrupt: true`), which causes checksum rejection and normal
  reroute/refund handling.

The MVP intentionally allows disputes after settlement so the accounting
behavior is explicit and testable: provider funds are moved into a hold, then
released or refunded by an idempotent resolution transaction. A later phase
can add pre-settlement holds and stronger domain-specific proof formats.

### 4. Provider reputation based on evidence

Reputation should not be a manually edited star rating. It should be calculated
from observed outcomes:

- Successful completion rate
- Independent verification agreement rate
- Median and tail latency
- Price accuracy
- Retry frequency
- Dispute frequency
- Refund frequency
- Evidence completeness
- Recent reliability decay

Every reputation score should show its evidence window and sample size. A new
provider with three successful jobs must not look as trustworthy as a provider
with ten thousand successful jobs.

### 5. A bounded dispute protocol

When a buyer rejects a result:

1. Payment moves from escrow to disputed state.
2. The buyer selects a reason from structured categories.
3. AEON freezes the evidence and policy versions.
4. A verifier reruns the job or checks the supplied evidence.
5. The provider can respond with additional evidence.
6. A policy engine recommends refund, partial payment, retry, or release.
7. A human can decide high-value or ambiguous cases.
8. The result updates reputation and the audit log.

This is more defensible than pretending every failed job can be automatically
resolved.

### 6. Provider selection as a trust-adjusted market

The buyer should not choose a provider using price alone. AEON should rank
eligible providers using a transparent score such as:

```text
selection score =
  price fit
  + reliability
  + verification strength
  + latency fit
  + policy compliance
  - recent risk
```

The dashboard should show why a provider was selected. Explainability is part of
the product, not just a debugging feature.

## What AEON already has that enables this

The current project already contains useful foundations:

- Consumer and provider agents
- Agent policies and allow-lists
- Price negotiation and deterministic fallback pricing
- Escrow-like trade processing
- HMAC-signed worker dispatch
- Nonce and timestamp protection
- Result checksums
- Worker metering
- Ledger entries and invariant checks
- Approvals and kill switch controls
- Audit records
- Live event stream
- MongoDB persistence
- React dashboard
- Judge mode for repeatable demonstrations

Therefore, the proposal is an extension of AEON's existing architecture, not a
complete rewrite.

## Recommended MVP

The first implementation should be deliberately narrow.

### MVP name

**AEON Verified Trade Network**

### MVP user promise

> “Before AEON releases payment, it can show what ran, who ran it, what evidence
> was produced, how confidently the result was verified, and what happens if the
> buyer disputes it.”

### MVP scope

1. Persist an evidence envelope for every worker execution.
2. Add a verification status and verification level to a trade.
3. Add a deterministic verifier for the existing demo jobs.
4. Add a structured dispute endpoint and dashboard panel.
5. Keep disputed funds locked until resolution.
6. Calculate a basic evidence-based provider reputation score.
7. Display the provider-selection explanation in the dashboard.
8. Add an end-to-end demo scenario:
   - successful verified trade
   - intentionally corrupted result
   - automatic dispute
   - verifier decision
   - refund or settlement

### Explicitly out of MVP

- Cryptocurrency or blockchain replacement
- Live PayPal money movement
- Trusted hardware attestation
- Arbitrary untrusted code execution
- Fully autonomous legal or financial dispute decisions
- A public multi-tenant marketplace
- A new payment protocol

## Proposed user experience

### Before running a trade

The operator sees:

- Candidate providers
- Price
- Reputation score
- Verification level available
- Recent success rate
- Estimated latency
- Selection reason

### During a trade

The event stream shows:

```text
policy.accepted
provider.selected
evidence.started
evidence.created
verification.started
verification.passed
escrow.released
trade.settled
```

### After a successful trade

The trade detail shows:

- Result summary
- Evidence envelope
- Verification level
- Input/output digests
- Worker and runtime
- CPU and wall time
- Policy checks
- Reputation impact

### After a failed or disputed trade

The trade detail shows:

- Failure reason
- Dispute status
- Evidence comparison
- Verifier decision
- Funds state
- Refund or settlement decision
- Reputation impact

## Architecture extension

### New backend concepts

Potential new collections or bounded modules:

- `execution_evidence`
- `verifications`
- `disputes`
- `provider_reputation_snapshots`
- `policy_versions`

These names are proposals, not final implementation requirements.

### New API surfaces

Potential endpoints:

```text
GET  /api/v1/trades/{trade_id}/evidence
POST /api/v1/trades/{trade_id}/verify
POST /api/v1/trades/{trade_id}/dispute
GET  /api/v1/trades/{trade_id}/dispute
GET  /api/v1/agents/{agent_id}/reputation
GET  /api/v1/providers/recommendations
```

Every mutating endpoint must preserve idempotency, authorization, audit
logging, and ledger safety.

### New worker contract

Worker results should add evidence fields while remaining backward-compatible:

```json
{
  "result": {},
  "checksum": "sha256...",
  "evidence": {
    "worker_id": "worker-atlas",
    "runtime_version": "1.0.0",
    "input_digest": "sha256...",
    "output_digest": "sha256...",
    "started_at": "...",
    "completed_at": "...",
    "cpu_seconds": 0.31,
    "verification_level": "signed_execution"
  }
}
```

The actual schema must be finalized during implementation planning.

## Success criteria

The proposal is successful only if it can demonstrate all of these:

1. A normal trade produces a durable evidence envelope.
2. The dashboard explains why a provider was selected.
3. A deterministic job can be independently verified.
4. A corrupted result is detected before final settlement.
5. Disputed funds remain locked.
6. A dispute resolves into refund, partial payment, or release.
7. Provider reputation changes from observed evidence.
8. Audit records explain each decision.
9. Existing successful trades still work.
10. Backend tests and dashboard build remain green.

## Risks and honest limitations

### Evidence is not automatically truth

A worker can honestly sign an incorrect result. Signatures prove origin and
integrity, not correctness. Independent verification and reproducible jobs are
needed for stronger claims.

### Reputation can be gamed

An attacker could create many identities or generate fake successful jobs.
Future work needs identity costs, organization verification, anomaly detection,
and confidence intervals.

### Disputes can become expensive

Re-running jobs consumes resources. AEON should use risk-based verification and
only apply expensive checks to high-value or suspicious trades.

### The market may not need another marketplace

The product should be validated with real users before adding public discovery,
tokens, or a large provider network.

## Validation plan before broad implementation

1. Interview at least five potential users:
   - AI platform engineers
   - API marketplace operators
   - compute providers
   - security engineers
   - finance/operations owners
2. Ask which failure is most expensive:
   - wrong result
   - overcharging
   - unavailable provider
   - weak audit trail
   - unauthorized agent spending
3. Run a small benchmark with deterministic jobs.
4. Measure verification cost, latency, and false positives.
5. Decide whether the first buyer is:
   - an agent platform
   - a compute marketplace
   - an enterprise operations team
   - an internal AI platform
6. Only then expand beyond the MVP.

## Approval gate

Before implementation, approve or change:

### Product direction

- [ ] Use **AEON Verified Trade Network** as the MVP direction.
- [ ] Focus on trust/evidence/disputes rather than building another directory.

### MVP features

- [ ] Evidence envelope
- [ ] Verification levels
- [ ] Deterministic verifier
- [ ] Dispute workflow
- [ ] Evidence-based reputation
- [ ] Provider selection explanation
- [ ] Corrupted-result demo scenario

### Constraints

- [x] Keep PayPal sandbox-only; require credentials and never simulate money movement.
- [ ] Do not add blockchain or cryptocurrency in the MVP.
- [ ] Do not expose arbitrary code execution.
- [ ] Preserve current trade, ledger, auth, and worker behavior.

Once approved, the next step should be a detailed implementation plan with
database schema, API contracts, worker contract changes, UI screens, migration
strategy, tests, and an ordered task breakdown.

## References

- [Fetch.ai Agentverse](https://www.fetch.ai/agentverse)
- [Fetch.ai Agentverse documentation](https://innovationlab.fetch.ai/resources/docs/agentverse/)
- [SingularityNET marketplace](https://marketplace.singularity.io/)
- [SingularityNET developer portal](https://dev.singularitynet.io/docs/)
- [SingularityNET MPE overview](https://dev.singularitynet.io/docs/mpe-overview/)
- [Akash providers and leases](https://akash.network/docs/learn/core-concepts/providers-leases/)
- [Coinbase x402 overview](https://docs.cdp.coinbase.com/x402/welcome)
- [Coinbase Pay with x402](https://docs.cdp.coinbase.com/payments/payment-acceptance/pay-with-x402)
