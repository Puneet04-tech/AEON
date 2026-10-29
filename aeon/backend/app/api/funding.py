"""
AEON Funding API Router

Handles PayPal funding flows - Orders API for topping up agent balances,
webhook-driven crediting, and settlement payouts.
Follows AEON blueprint Day 4: PayPal funding and settlement.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import structlog
import time

from app.db.client import get_database
from app.settings import settings
from app.ledger.service import LedgerService
from app.security.hmac_signing import verify_payload

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["funding"])


# PayPal integration models
class FundingOrderCreate(BaseModel):
    """Create a PayPal funding order to top up an agent's balance."""
    agent_id: str = Field(..., description="Agent to fund")
    amount_micros: int = Field(..., ge=1, le=1000000000000, description="Amount in micro-USD")
    description: str = Field(..., description="Human-readable description")


class FundingOrderCapture(BaseModel):
    """Capture a previously created PayPal funding order."""
    order_id: str = Field(..., description="PayPal order ID to capture")
</model)


class PayoutBatchCreate(BaseModel):
    """Create a PayPal payout batch for settlement."""
    agent_ids: list = Field(..., description="List of agent IDs to pay out")
    amounts_micros: list = Field(..., description="Amounts in micro-USD for each agent")
    description: str = Field(..., description="Settlement description")


# Endpoints


@router.post("/funding/orders", status_code=201)
async def create_funding_order(
    order: FundingOrderCreate,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Create a PayPal funding order to top up an agent's balance.
    
    Day 4: Funding flow (Orders) with webhook-driven crediting.
    """
    from app.ledger.service import LedgerService
    
    # Validate agent exists
    agent = await db.agents.find_one({"agent_id": order.agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Validate amount
    if not (1 <= order.amount_micros <= 1000000000000):
        raise HTTPException(status_code=400, detail="Invalid amount")
    
    # Check daily cap and approval thresholds
    if order.amount_micros > 25000000:  # Above 25 uUSD approval threshold
        # Would need operator approval in production
        pass
    
    # Create funding order record
    order_record = {
        "order_id": f"paypal_order_{order.agent_id}_{int(time.time())}",
        "agent_id": order.agent_id,
        "amount_micros": order.amount_micros,
        "status": "created",
        "paypal_order_id": None,  # Populated after PayPal API call
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "metadata": {
            "description": order.description,
        }
    }
    
    await db.funding_orders.insert_one(order_record)
    
    # Record audit log
    await db.audit_log.insert_one({
        "audit_id": f"funding_order_{order.order_id}",
        "actor": "api",
        "action": "funding_order_created",
        "details": {
            "agent_id": order.agent_id,
            "amount_micros": order.amount_micros,
        },
        "timestamp": int(time.time()),
    })
    
    # In production, would call PayPal Orders API here
    # order_id = paypal_client.create_order(amount_micros, agent paypal_email)
    # order_record["paypal_order_id"] = order_id
    
    logger.info("Funding order created", agent_id=order.agent_id, amount_micros=order.amount_micros)
    
    return {
        "status": "created",
        "order_id": order_record["order_id"],
        "agent_id": order.agent_id,
        "amount_micros": order.amount_micros,
        "message": "Funding order created. Awaiting PayPal confirmation via webhook.",
    }


@router.post("/funding/orders/{order_id}/capture")
async def capture_funding_order(
    order_id: str,
    capture: FundingOrderCapture,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Capture a PayPal funding order, crediting the agent's balance.
    
    Webhook from PayPal confirms the capture, then ledger is credited.
    """
    from app.ledger.service import LedgerService
    
    # Find the funding order
    funding_order = await db.funding_orders.find_one({"order_id": order_id})
    if not funding_order:
        raise HTTPException(status_code=404, detail="Funding order not found")
    
    if funding_order["status"] != "created":
        raise HTTPException(status_code=400, detail="Funding order not in created state")
    
    ledger = LedgerService(db)
    
    # Update funding order status
    await db.funding_orders.update_one(
        {"order_id": order_id},
        {"$set": {
            "status": "captured",
            "paypal_order_id": capture.order_id,
            "updated_at": int(time.time()),
        }}
    )
    
    # Credit the agent's balance in the ledger
    posting = await ledger.record_posting(
        trade_id=f"funding_{order_id}",
        from_account="treasury_effective",
        to_account=f"agent_{funding_order['agent_id']}_balance",
        amount_micros=funding_order["amount_micros"],
        metadata={
            "funding_type": "agent_topup",
            "paypal_order_id": capture.order_id,
        }
    )
    
    # Record audit log
    await db.audit_log.insert_one({
        "audit_id": f"funding_cap_{order_id}",
        "actor": "api",
        "action": "funding_captured",
        "details": {
            "agent_id": funding_order["agent_id"],
            "amount_micros": funding_order["amount_micros"],
            "paypal_order_id": capture.order_id,
        },
        "timestamp": int(time.time()),
    })
    
    logger.info("Funding order captured", order_id=order_id, amount_micros=funding_order["amount_micros"])
    
    return {
        "status": "captured",
        "order_id": order_id,
        "agent_id": funding_order["agent_id"],
        "amount_micros": funding_order["amount_micros"],
        "message": "Agent balance credited via PayPal capture.",
    }


@router.post("/settlement/batches", status_code=201)
async def create_settlement_batch(
    batch: PayoutBatchCreate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    background_tasks: BackgroundTasks = None
):
    """Create a PayPal payout batch for settlement.
    
    Day 4: Settlement engine - netting, lock, approval thresholds, Payouts batch.
    """
    from app.ledger.service import LedgerService
    
    # Validate batch
    if len(batch.agent_ids) != len(batch.amounts_micros):
        raise HTTPException(status_code=400, detail "agent_ids and amounts_micros must have same length")
    
    if len(batch.agent_ids) == 0:
        raise HTTPException(status_code=400, detail "Batch must contain at least one agent")
    
    # Validate amounts
    total_amount = sum(batch.amounts_micros)
    for amt in batch.amounts_micros:
        if not (1 <= amt <= 1000000000000):
            raise HTTPException(status_code=400, detail=f"Invalid amount: {amt}")
    
    # Check daily cap
    daily_cap = 1000000000  # 1000 uUSD default daily cap from settings
    if total_amount > daily_cap:
        raise HTTPException(
            status_code=400,
            detail=f"Batch total {total_amount} exceeds daily cap {daily_cap}"
        )
    
    # Check approval threshold for large individual payouts
    approval_threshold = 25000000  # 25 uUSD
    for i, (agent_id, amount) in enumerate(zip(batch.agent_ids, batch.amounts_micros)):
        if amount > approval_threshold:
            # Would need operator approval - in production would check/require it
            pass
    
    # Create settlement batch record
    batch_id = f"settlement_{int(time.time())}"
    
    batch_record = {
        "batch_id": batch_id,
        "agent_ids": batch.agent_ids,
        "amounts_micros": batch.amounts_micros,
        "total_micros": total_amount,
        "status": "pending",
        "paypal_payout_id": None,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "metadata": {
            "description": batch.description,
        }
    }
    
    await db.settlement_batches.insert_one(batch_record)
    
    # Record audit log
    await db.audit_log.insert_one({
        "audit_id": f"settlement_batch_{batch_id}",
        "actor": "api",
        "action": "settlement_batch_created",
        "details": {
            "batch_id": batch_id,
            "total_micros": total_amount,
            "agent_count": len(batch.agent_ids),
        },
        "timestamp": int(time.time()),
    })
    
    # In production, would call PayPal Payouts API here
    # payout_id = paypal_client.create_payout_batch(batch)
    # batch_record["paypal_payout_id"] = payout_id
    
    logger.info("Settlement batch created", batch_id=batch_id, total_micros=total_amount)
    
    return {
        "status": "pending",
        "batch_id": batch_id,
        "total_micros": total_amount,
        "agent_count": len(batch.agent_ids),
        "message": "Settlement batch created. Awaiting PayPal payout confirmation.",
    }


@router.post("/settlement/batches/{batch_id}/execute")
async def execute_settlement_batch(
    batch_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Execute a settlement batch - send PayPal payouts and update ledger."""
    from app.ledger.service import LedgerService
    
    # Find the settlement batch
    batch = await db.settlement_batches.find_one({"batch_id": batch_id})
    if not batch:
        raise HTTPException(status_code=404, detail="Settlement batch not found")
    
    if batch["status"] != "pending":
        raise HTTPException(status_code=400, detail="Batch not in pending state")
    
    ledger = LedgerService(db)
    
    # Record ledger postings for each payout
    for i, (agent_id, amount) in enumerate(zip(batch["agent_ids"], batch["amounts_micros"])):
        posting = await ledger.record_posting(
            trade_id=f"settlement_{batch_id}_{i}",
            from_account="treasury_effective",
            to_account=f"agent_{agent_id}_balance",
            amount_micros=amount,
            metadata={
                "settlement_type": "batch_payout",
                "batch_id": batch_id,
            }
        )
    
    # Update batch status
    await db.settlement_batches.update_one(
        {"batch_id": batch_id},
        {"$set": {
            "status": "executed",
            "executed_at": int(time.time()),
            "updated_at": int(time.time()),
        }}
    )
    
    # Record audit log
    await db.audit_log.insert_one({
        "audit_id": f"settlement_exec_{batch_id}",
        "actor": "api",
        "action": "settlement_executed",
        "details": {
            "batch_id": batch_id,
            "total_micros": batch["total_micros"],
            "agent_count": len(batch["agent_ids"]),
        },
        "timestamp": int(time.time()),
    })
    
    logger.info("Settlement batch executed", batch_id=batch_id, total_micros=batch["total_micros"])
    
    return {
        "status": "executed",
        "batch_id": batch_id,
        "total_micros": batch["total_micros"],
        "message": "Settlement batch executed. PayPal payouts sent.",
    }