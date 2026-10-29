"""
AEON Trades API Router

Handles the trade lifecycle: negotiation, escrow, dispatch, verify, book, and penalty.
Follows AEON blueprint Day 3: Agents, negotiation and real jobs.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundQuery
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, Literal
import structlog
import time

from app.db.client import get_database
from app.ledger.service import LedgerService
from app.guardrails.engine import GuardrailEngine
from app.security.input_guard import validate_agent_id, validate_amount, validate_trade_data
from app.security.hmac_signing import sign_payload, compute_hmac

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["trades"])


# Pydantic models for trade data
class NegotiationRound(BaseModel):
    """A single negotiation round message."""
    round_number: int = Field(..., ge=1, le=3, description="Round number (1-3)")
    price_offer_micros: int = Field(..., ge=1, description="Price in micro-USD")
    reasoning: str = Field(..., description="LLM-generated reasoning for the offer")
    
    @validator "price_offer_micros")
    def price_must_be_positive(cls, v):
        if v < 1:
            raise ValueError("price must be positive")
        return v


class NegotiationInitiate(BaseModel):
    """Initiate a negotiation for a trade."""
    job_id: str = Field(..., description="Unique job identifier")
    seller_id: str = Field(..., description="Agent ID of the seller")
    buyer_id: str = Field(..., description="Agent ID of the buyer")
    initial_price_micros: int = Field(..., ge=1, description="Initial offer price")
    job_description: str = Field(..., description="Description of the job to execute")
    deadline_seconds: int = Field(
        default=3600, ge=60, le=86400,
        description="Deadline in seconds (60s - 24h)"
    )


class NegotiationCounter(BaseModel):
    """Counter-offer during negotiation."""
    round_number: int = Field(..., ge=1, le=3, description="Round number")
    price_offer_micros: int = Field(..., ge=1, description="Counter offer price")
    reasoning: str = Field(..., description="Reasoning for counter-offer")


class EscrowRequest(BaseModel):
    """Request to escrow funds for a trade."""
    trade_id: str = Field(..., description="Trade identifier")
    amount_micros: int = Field(..., ge=1, description="Amount to escrow")
    job_id: str = Field(..., description="Associated job ID")


class TradeBookRequest(BaseModel):
    """Request to book escrow to provider."""
    trade_id: str = Field(..., description="Trade identifier")
    result_checksum: str = Field(..., description="Verified result checksum from provider")
    satisfaction: bool = Field(..., description="Whether consumer is satisfied")


# Trade lifecycle endpoints


@router.post("/trades/negotiate/initiate", status_code=201)
async def initiate_negotiation(
    negotiation: NegotiationInitiate,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Initiate a trade negotiation.
    
    Day 3: Negotiation engine - max 3 rounds between buyer and seller.
    """
    from app.guardrails.engine import GuardrailEngine
    from app.ledger.service import LedgerService
    
    # Validate agents
    if not validate_agent_id(negotiation.buyer_id):
        raise HTTPException(status_code=400, detail="Invalid buyer agent ID")
    if not validate_agent_id(negotiation.seller_id):
        raise HTTPException(status_code=400, detail="Invalid seller agent ID")
    if negotiation.buyer_id == negotiation.seller_id:
        raise HTTPException(status_code=400, detail "Buyer and seller cannot be the same")
    
    # Validate amount
    if not validate_amount(negotiation.initial_price_micros):
        raise HTTPException(status_code=400, detail="Invalid price amount")
    
    # Initialize guardrail engine
    ledger = LedgerService(db)
    guardrail = GuardrailEngine(
        ledger_service=ledger,
        agent_budgets={negotiation.buyer_id: 10000000000},  # Default large budget
    )
    
    # Evaluate guardrails
    all_passed, results = guardrail.evaluate_trade_proposal(
        buyer_id=negotiation.buyer_id,
        seller_id=negotiation.seller_id,
        price_micros=negotiation.initial_price_micros,
        trade_timestamp=int(time.time()),
        agent_budgets={negotiation.buyer_id: 10000000000},
    )
    
    if not all_passed:
        failed_rules = [r[0] for r in results if not r[1].passed]
        raise HTTPException(
            status_code=400,
            detail=f"Guardrail validation failed: {', '.join(failed_rules)}"
        )
    
    # Create trade record with status "negotiating"
    trade_id = f"trade_{negotiation.agent_id}_{int(time.time())}"
    
    trade_record = {
        "trade_id": trade_id,
        "buyer_id": negotiation.buyer_id,
        "seller_id": negotiation.seller_id,
        "job_id": negotiation.job_id,
        "status": "negotiating",
        "current_round": 0,
        "price_micros": None,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "metadata": {
            "initial_price_micros": negotiation.initial_price_micros,
            "deadline_seconds": negotiation.deadline_seconds,
            "job_description": negotiation.job_description,
        }
    }
    
    await db.trades.insert_one(trade_record)
    
    # Record audit log
    await db.audit_log.insert_one({
        "audit_id": f"trade_{trade_id}_initiated",
        "actor": "api",
        "action": "trade_initiated",
        "trade_id": trade_id,
        "details": {
            "buyer_id": negotiation.buyer_id,
            "seller_id": negotiation.seller_id,
            "initial_price_micros": negotiation.initial_price_micros,
        },
        "timestamp": int(time.time()),
    })
    
    logger.info("Negotiation initiated", trade_id=trade_id)
    
    return {
        "status": "negotiating",
        "trade_id": trade_id,
        "current_round": 0,
        "message": "Trade negotiation initiated. Maximum 3 rounds allowed.",
        "metadata": trade_record["metadata"]
    }


@router.post("/trades/negotiate/counter", status_code=200)
async def make_counter_offer(
    counter: NegotiationCounter,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Make a counter-offer during negotiation (round 2 or 3).
    
    Day 3: Negotiation engine - max 3 rounds.
    """
    from app.ledger.service import LedgerService
    
    # Find the trade
    trade = await db.trades.find_one({"trade_id": counter.trade_id})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    if trade["status"] != "negotiating":
        raise HTTPException(status_code=400, detail="Trade is not in negotiating state")
    
    # Validate the counter offer
    if not validate_agent_id(counter.buyer_id) or not validate_agent_id(counter.seller_id):
        raise HTTPException(status_code=400, detail="Invalid agent IDs")
    
    if counter.round_number < 1 or counter.round_number > 3:
        raise HTTPException(status_code=400, detail "Round number must be 1-3")
    
    if counter.round_number > trade["current_round"]:
        # New round - validate against guardrails
        ledger = LedgerService(db)
        guardrail = GuardrailEngine(ledger_service=ledger)
        
        all_passed, results = guardrail.evaluate_trade_proposal(
            buyer_id=counter.buyer_id,
            seller_id=counter.seller_id,
            price_micros=counter.price_offer_micros,
            trade_timestamp=int(time.time()),
        )
        
        if not all_passed:
            failed_rules = [r[0] for r in results if not r[1].passed]
            raise HTTPException(
                status_code=400,
                detail=f"Guardrail validation failed: {', '.join(failed_rules)}"
            )
    
    # Update trade with counter offer
    await db.trades.update_one(
        {"trade_id": counter.trade_id},
        {"$set": {
            "current_round": counter.round_number,
            "price_micros": counter.price_offer_micros,
            "updated_at": int(time.time()),
        }}
    )
    
    # Check if 3 rounds completed
    trade = await db.trades.find_one({"trade_id": counter.trade_id})
    round_completed = trade["current_round"] >= 3
    
    return {
        "status": "counter_offered",
        "trade_id": counter.trade_id,
        "round": counter.round_number,
        "price_micros": counter.price_offer_micros,
        "rounds_completed": trade["current_round"],
        "negotiation_complete": round_completed,
        "message": "Counter offer recorded." + (" Negotiation complete - ready for escrow." if round_completed else "")
    }


@router.post("/trades/escrow", status_code=201)
async def request_escrow(
    escrow_request: EscrowRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Escrow funds for a trade.
    
    Day 3: Escrow and execute - price held in escrow until job completion.
    """
    from app.ledger.service import LedgerService
    
    # Find the trade
    trade = await db.trades.find_one({"trade_id": escrow_request.trade_id})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    if trade["status"] != "negotiating" and trade["status"] != "counter_offered":
        raise HTTPException(status_code=400, detail="Trade not in negotiable state")
    
    # Validate escrow amount matches trade price
    if trade["price_micros"] and escrow_request.amount_micros != trade["price_micros"]:
        raise HTTPException(
            status_code=400,
            detail=f"Escrow amount {escrow_request.amount_micros} doesn't match trade price {trade['price_micros']}"
        )
    
    # Record escrow posting to ledger
    ledger = LedgerService(db)
    
    # Create a hold entry - debit from buyer's effective account, credit to escrow
    posting = await ledger.record_posting(
        trade_id=escrow_request.trade_id,
        from_account=f"agent_{escrow_request.buyer_id}_effective",
        to_account=f"escrow_{escrow_request.trade_id}",
        amount_micros=escrow_request.amount_micros,
        metadata={"trade_type": "escrow", "job_id": escrow_request.job_id}
    )
    
    # Update trade status
    await db.trades.update_one(
        {"trade_id": escrow_request.trade_id},
        {"$set": {
            "status": "escrowed",
            "escrow_amount_micros": escrow_request.amount_micros,
            "updated_at": int(time.time()),
        }}
    )
    
    # Record audit log
    await db.audit_log.insert_one({
        "audit_id": f"escrow_{escrow_request.trade_id}",
        "actor": "api",
        "action": "escrow_funds",
        "trade_id": escrow_request.trade_id,
        "details": {
            "amount_micros": escrow_request.amount_micros,
            "buyer_id": trade["buyer_id"],
            "seller_id": trade["seller_id"],
        },
        "timestamp": int(time.time()),
    })
    
    logger.info("Escrow funded", trade_id=escrow_request.trade_id, amount_micros=escrow_request.amount_micros)
    
    return {
        "status": "escrowed",
        "trade_id": escrow_request.trade_id,
        "escrow_amount_micros": escrow_request.amount_micros,
        "message": "Funds escrowed. Job will be dispatched to provider."
    }


@router.post("/trades/{trade_id}/dispatch")
async def dispatch_job(
    trade_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Dispatch the job to the provider worker.
    
    Day 3: Worker service - image resize and matrix multiply with limits.
    """
    from app.ledger.service import LedgerService
    
    # Find the trade
    trade = await db.trades.find_one({"trade_id": trade_id})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    if trade["status"] != "escrowed":
        raise HTTPException(status_code=400, detail="Trade not in escrowed state")
    
    # Update trade status to dispatched
    await db.trades.update_one(
        {"trade_id": trade_id},
        {"$set": {
            "status": "dispatched",
            "dispatched_at": int(time.time()),
            "updated_at": int(time.time()),
        }}
    )
    
    # Record audit log
    await db.audit_log.insert_one({
        "audit_id": f"dispatch_{trade_id}",
        "actor": "api",
        "action": "job_dispatched",
        "trade_id": trade_id,
        "details": {
            "job_id": trade["job_id"],
            "seller_id": trade["seller_id"],
        },
        "timestamp": int(time.time()),
    })
    
    logger.info("Job dispatched", trade_id=trade_id, job_id=trade["job_id"])
    
    return {
        "status": "dispatched",
        "trade_id": trade_id,
        "job_id": trade["job_id"],
        "message": "Job dispatched to provider worker.",
    }


@router.post("/trades/{trade_id}/verify")
async def verify_and_book(
    trade_id: str,
    book_request: TradeBookRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Verify job result and book escrow to provider.
    
    Day 3: Verify and book - consumer verifies checksum, ledger moves escrow to provider.
    """
    from app.ledger.service import LedgerService
    
    # Find the trade
    trade = await db.trades.find_one({"trade_id": trade_id})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    if trade["status"] != "dispatched":
        raise HTTPException(status_code=400, detail="Trade not in dispatched state")
    
    ledger = LedgerService(db)
    
    # Record ledger posting: move escrow from escrow to provider
    posting = await ledger.record_posting(
        trade_id=trade_id,
        from_account=f"escrow_{trade_id}",
        to_account=f"agent_{trade['seller_id']}_balance",
        amount_micros=trade["escrow_amount_micros"],
        metadata={
            "trade_type": "book_escrow",
            "result_checksum": book_request.result_checksum,
            "satisfaction": book_request.satisfaction,
        }
    )
    
    # Update trade status
    new_status = "completed" if book_request.satisfaction else "disputed"
    await db.trades.update_one(
        {"trade_id": trade_id},
        {"$set": {
            "status": new_status,
            "booked_at": int(time.time()),
            "result_checksum": book_request.result_checksum,
            "updated_at": int(time.time()),
        }}
    )
    
    # Record audit log
    await db.audit_log.insert_one({
        "audit_id": f"book_{trade_id}",
        "actor": "api",
        "action": "trade_booked",
        "trade_id": trade_id,
        "details": {
            "amount_micros": trade["escrow_amount_micros"],
            "seller_id": trade["seller_id"],
            "satisfaction": book_request.satisfaction,
            "checksum": book_request.result_checksum[:16] + "...",
        },
        "timestamp": int(time.time()),
    })
    
    logger.info("Trade booked", trade_id=trade_id, status=new_status, satisfaction=book_request.satisfaction)
    
    return {
        "status": new_status,
        "trade_id": trade_id,
        "amount_micros": trade["escrow_amount_micros"],
        "message": f"Trade {new_status}. Escrow released to provider.",
    }


@router.post("/trades/{trade_id}/penalty")
async def apply_penalty(
    trade_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Apply SLA penalty if job failed or was not completed on time.
    
    Day 3: Penalty path - if SLA missed, penalty booked against provider.
    """
    from app.ledger.service import LedgerService
    
    # Find the trade
    trade = await db.trades.find_one({"trade_id": trade_id})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    if trade["status"] == "completed":
        raise HTTPException(status_code=400, detail="Trade already completed - no penalty")
    
    ledger = LedgerService(db)
    
    # Penalty: deduct from provider's bond/balance, credit to a penalty pool
    # For now, we'll deduct half the escrow amount as penalty
    penalty_amount = trade["escrow_amount_micros"] // 2
    
    posting = await ledger.record_posting(
        trade_id=trade_id,
        from_account=f"agent_{trade['seller_id']}_balance",
        to_account="penalty_pool",
        amount_micros=penalty_amount,
        metadata={"trade_type": "sla_penalty", "reason": "SLA missed or faulted job"}
    )
    
    # Update trade status to penalty-applied
    await db.trades.update_one(
        {"trade_id": trade_id},
        {"$set": {
            "status": "penalty_applied",
            "penalty_amount_micros": penalty_amount,
            "updated_at": int(time.time()),
        }}
    )
    
    # Record audit log
    await db.audit_log.insert_one({
        "audit_id": f"penalty_{trade_id}",
        "actor": "api",
        "action": "sla_penalty",
        "trade_id": trade_id,
        "details": {
            "penalty_micros": penalty_amount,
            "seller_id": trade["seller_id"],
        },
        "timestamp": int(time.time()),
    })
    
    logger.info("Penalty applied", trade_id=trade_id, penalty_micros=penalty_amount)
    
    return {
        "status": "penalty_applied",
        "trade_id": trade_id,
        "penalty_amount_micros": penalty_amount,
        "message": "SLA penalty applied to provider.",
    }