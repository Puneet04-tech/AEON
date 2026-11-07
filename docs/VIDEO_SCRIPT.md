# AEON — Demo Video Script (2:50, ≤3 min limit)

**Rule of thumb:** every second must show the product or say something judges score.
Do not show setup, terminals, or code unless it's the HMAC signature line for 3 seconds.

---

## SHOT LIST (record at 1080p, zoom browser to 125%, use the DEPLOYED site)

### 0:00–0:20 — Hook + problem (talking over the login screen)
> "AI agents can already *do* work for each other — but they can't safely *pay* each other.
> Card rails can't settle a four-cent job, strangers don't trust strangers, and nobody hands an
> autonomous agent an unbounded wallet."
>
> **On screen:** login page. Click "Create account", type email + password, hit Create.
> (This doubles as proof signup works — no faked credentials.)

### 0:20–0:40 — The pitch (over the loaded console)
> "This is AEON — a clearing house for agent commerce. Agents negotiate a price with AI,
> the clearing house escrows the funds, a real job runs on a real signed worker, the result is
> verified cryptographically, and only then does money move — all on PayPal rails, settled
> through one netted payout batch."

**On screen:** full dashboard — point out (mouse only, fast): Kill Switch chip, INVARIANT 0 µUSD,
agent topology canvas, event stream already ticking.

### 0:40–1:25 — THE CORE DEMO: one full trade (Run Trade dialog → topology → transcript)
1. Click ⚡ **Run Trade**, pick Atlas → Cirrus, `image_resize`, submit.
2. **Watch the topology:** money-flow edge animates Atlas→Cirrus; node balances update.
3. Click the new trade row → **negotiation transcript** in the right drawer.
   Read one line aloud: "The buyer agent opens at X, the seller counters, guardrails clamp
   anything out of policy — the LLM *proposes*, code *decides*."
4. Scroll the event stream: `created → escrowed → dispatched → delivered → verified → settled`.
5. Point at **INVARIANT 0 µUSD** staying green: "double-entry ledger — every posting balances,
   every second."

### 1:25–1:50 — PayPal is REAL (funding + payout)
1. **Fund Agent** dialog → PayPal order opens (show the sandbox PayPal tab for 3 s) → approve →
   Capture. Toast: "Funded ... (sandbox)".
2. **Settle** → Payouts tab in AG Grid: batch with PayPal item IDs, state COMPLETED.
> "Real PayPal Orders API for funding, real Payouts API for settlement, webhook signature
> verification on every callback. Sandbox — no real money."

### 1:50–2:15 — Trust machinery (the differentiator)
1. AG Grid **Ledger** tab: balanced postings, integer micro-USD.
2. **Audit** tab: append-only record scrolling.
3. Chaos: corrupt a worker → run a trade → show **rejection → refund → bond penalty → reroute**
   to the other provider, all visible in events.
> "When work fails, the buyer is refunded automatically, the provider's bond is penalised, and
> the job reroutes. Trust isn't a promise here — it's accounting."

### 2:15–2:35 — AG Grid + human control (sponsor beats)
1. Flip between Trades/Ledger/Payouts/Approvals tabs quickly — "every data surface is AG Grid,
   monospace tabular numerals, dark and light themes."
2. Open **Approvals**, approve a threshold trade as the human: "humans stay on the loop."

### 2:35–2:50 — Close (over topology with several edges glowing)
> "Five agents, real workers, real PayPal, AI negotiation with personalities and deadline
> pressure — the full transaction loop for the machine economy: policy, escrow, evidence,
> verification, reputation, settlement. AEON: the clearing house agents can trust.
> Built with PayPal, AG Grid, and Render — live demo and source below."

---

## RECORDING CHECKLIST
- [ ] Warm the site first (open it, wait, reload) — NO cold start on camera
- [ ] Dark theme (default) — it reads "command center" on video
- [ ] Reset demo state before recording so agent balances look fresh
- [ ] Do one full dry run before the "real" take; keep the real take under 3:00
- [ ] No copyrighted music; voice-over recorded separately (Audacity/phone) is fine
- [ ] End card (last 3 s): repo URL + live URL text on screen
