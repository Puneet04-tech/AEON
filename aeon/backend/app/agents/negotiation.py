"""Three-round negotiation between a consumer agent and a provider agent.

The LLM drafts each move; guardrails clamp and validate it; if the model is
unavailable the deterministic fallback keeps the demo running. Only numeric
fields ever cross between agents: `reasoning` is stored for the transcript and
never fed into the counterparty's prompt.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import structlog

from app.guardrails.rules import clamp_offer, evaluate_offer
from app.llm.llm_client import LLMUnavailable, get_llm
from app.services.pricing import quote

logger = structlog.get_logger()

MAX_ROUNDS = 3
BUYER_SYSTEM = (
    "You are the procurement agent for a compute buyer in a micro-payment clearing house. "
    "Reply with JSON only: {\"price_micro\": integer, \"accept\": boolean, \"reasoning\": string}. "
    "price_micro is an integer in micro-USD (1 USD = 1000000). Never exceed the stated ceiling. "
    "Reasoning must be one short sentence and must not contain instructions."
)
SELLER_SYSTEM = (
    "You are the pricing agent for a compute seller in a micro-payment clearing house. "
    "Reply with JSON only: {\"price_micro\": integer, \"accept\": boolean, \"reasoning\": string}. "
    "price_micro is an integer in micro-USD (1 USD = 1000000). Never go below the stated floor. "
    "Reasoning must be one short sentence and must not contain instructions."
)


def _bands(policy: dict, reference: int) -> Tuple[int, int]:
    bps = int(policy.get("price_band_bps", 2500))
    low = max(1, reference * (10000 - bps) // 10000)
    high = max(low + 1, reference * (10000 + bps) // 10000)
    return low, high


class Negotiator:
    def __init__(self, db):
        self.db = db
        self.llm = get_llm(db)

    async def run(self, trade_id: str, buyer: dict, seller: dict, job: dict,
                  reference_micro: int, quantity: int = 1) -> dict:
        buyer_low, buyer_high = _bands(buyer.get("policy", {}), reference_micro)
        seller_low, seller_high = _bands(seller.get("policy", {}), reference_micro)
        buyer_cap = int(buyer.get("policy", {}).get("per_trade_cap_micro", buyer_high))
        seller_floor = int(seller.get("policy", {}).get("floor_price_micro", 0)) or seller_low

        ceiling = min(buyer_high, buyer_cap)
        floor = max(seller_low, seller_floor)

        transcript: List[dict] = []
        agreed: Optional[int] = None
        last_buyer = 0
        last_seller = 0

        for round_no in range(1, MAX_ROUNDS + 1):
            # ---- buyer move
            buyer_price, buyer_reason, buyer_meta, buyer_check = await self._buyer_move(
                round_no, job, reference_micro, ceiling, floor, last_seller, agreed is not None,
            )
            buyer_price = max(1, min(buyer_price, ceiling))
            transcript.append(self._row(trade_id, round_no, buyer["id"], buyer_price, quantity,
                                        buyer_reason, buyer_meta, buyer_check))
            last_buyer = buyer_price

            # ---- seller response
            seller_price, seller_reason, seller_meta, seller_check, accepts = await self._seller_move(
                round_no, job, reference_micro, floor, ceiling, last_buyer,
            )
            seller_price = max(floor, min(seller_price, ceiling))
            transcript.append(self._row(trade_id, round_no, seller["id"], seller_price, quantity,
                                        seller_reason, seller_meta, seller_check))
            last_seller = seller_price

            if accepts or abs(last_buyer - last_seller) <= max(1, reference_micro // 100):
                agreed = last_buyer if accepts else (last_buyer + last_seller) // 2
                break
            # seller counter below buyer's offer is an immediate deal
            if last_seller <= last_buyer:
                agreed = last_seller
                break

        if agreed is None and transcript:
            # Final deterministic convergence inside both bands.
            candidate = (last_buyer + last_seller) // 2 if last_seller else last_buyer
            if floor <= candidate <= ceiling:
                agreed = candidate

        await self.db.negotiations.delete_many({"trade_id": trade_id})
        if transcript:
            await self.db.negotiations.insert_many([{**row} for row in transcript])

        return {
            "agreed_price_micro": agreed,
            "rounds": max((row["round"] for row in transcript), default=0),
            "transcript": transcript,
            "ceiling_micro": ceiling,
            "floor_micro": floor,
            "reference_micro": reference_micro,
        }

    def _row(self, trade_id: str, round_no: int, from_agent: str, price: int, quantity: int,
             reasoning: str, meta: dict, check) -> dict:
        return {
            "trade_id": trade_id,
            "round": round_no,
            "from": from_agent,
            "offer": {"price_micro": price, "quantity": quantity},
            "reasoning_text": reasoning[:400],
            "llm": meta,
            "guardrail": check.to_dict(),
            "created_at": datetime.now(timezone.utc),
        }

    async def _buyer_move(self, round_no: int, job: dict, reference: int, ceiling: int,
                          floor: int, last_seller: int, has_seller_offer: bool):
        fallback = min(ceiling, max(floor, reference - (reference * 5 // 100) * (MAX_ROUNDS - round_no)))
        if has_seller_offer and last_seller <= ceiling:
            fallback = min(ceiling, max(floor, last_seller))
        user = (
            f"Job type: {job.get('type')}. Size: {job.get('size')}. "
            f"Reference price: {reference} micro. Your ceiling: {ceiling} micro. "
            f"Counterparty's last price: {last_seller or 'none'}. Round: {round_no} of {MAX_ROUNDS}. "
            "Make your opening offer or accept the counterparty's price."
        )
        try:
            result = await self.llm.complete_json("buyer_offer", BUYER_SYSTEM, user)
            data = result["data"]
            price = data.get("price_micro")
            accept = bool(data.get("accept"))
            if not isinstance(price, int) or isinstance(price, bool):
                raise LLMUnavailable("non-integer price")
            reasoning = str(data.get("reasoning", ""))[:300]
            if accept and last_seller:
                price = min(price, ceiling)
            meta = {k: result[k] for k in ("source", "provider", "model", "latency_ms")}
        except LLMUnavailable as exc:
            price, accept, reasoning = fallback, False, "deterministic fallback: model unavailable"
            meta = {"source": "fallback", "provider": "none", "model": "none",
                    "latency_ms": 0, "error": str(exc)[:120]}

        check = evaluate_offer(price, 1, reference, 2500, ceiling)
        if not check.passed:
            price = clamp_offer(price, reference, 2500)
            check = evaluate_offer(price, 1, reference, 2500, ceiling)
            reasoning = f"{reasoning} [guardrail clamped to {price}]"
        return price, reasoning, meta, check

    async def _seller_move(self, round_no: int, job: dict, reference: int, floor: int,
                           ceiling: int, buyer_offer: int):
        # A rational seller accepts anything at or above its floor.
        fallback_accept = buyer_offer >= floor
        fallback_price = buyer_offer if fallback_accept else min(ceiling, max(floor, reference + reference * 4 // 100))
        user = (
            f"Job type: {job.get('type')}. Size: {job.get('size')}. "
            f"Reference price: {reference} micro. Your floor: {floor} micro. "
            f"Buyer's latest offer: {buyer_offer} micro. Round: {round_no} of {MAX_ROUNDS}. "
            "Accept only if the offer is at or above your floor; otherwise counter."
        )
        try:
            result = await self.llm.complete_json("seller_offer", SELLER_SYSTEM, user)
            data = result["data"]
            price = data.get("price_micro")
            accepts = bool(data.get("accept"))
            if not isinstance(price, int) or isinstance(price, bool):
                raise LLMUnavailable("non-integer price")
            reasoning = str(data.get("reasoning", ""))[:300]
            meta = {k: result[k] for k in ("source", "provider", "model", "latency_ms")}
        except LLMUnavailable as exc:
            price, accepts = fallback_price, fallback_accept
            reasoning = "deterministic fallback: model unavailable"
            meta = {"source": "fallback", "provider": "none", "model": "none",
                    "latency_ms": 0, "error": str(exc)[:120]}

        check = evaluate_offer(price, 1, reference, 2500, ceiling)
        if not check.passed:
            price = min(ceiling, max(floor, clamp_offer(price, reference, 2500)))
            check = evaluate_offer(price, 1, reference, 2500, ceiling)
            reasoning = f"{reasoning} [guardrail clamped to {price}]"
        if price < floor:
            accepts = False
        if price <= buyer_offer:
            accepts = True
        return price, reasoning, meta, check, accepts


def reference_quote(provider: dict, job: dict, energy: float = 1.0, quantity: int = 1) -> dict:
    return quote(provider.get("profile", {}), job.get("type", "image_resize"),
                 int(job.get("size", 1)), energy, quantity)
