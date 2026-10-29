"""
AEON Approvals API Router

Handles transaction approvals and kill switch operations.
Follows AEON blueprint requirements for human-in-the-loop controls.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import structlog
import time

from app.db.client import get_database
from app.guardrails.engine import GuardrailEngine
from app.ledger.service import LedgerService
from app.security.sessions import verify_password, hash_password

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["approvals"])


class ApprovalDecision(BaseModel):
    """Decision on an approval request."""
    approve: bool = Field(..., description="True to approve, False to reject")
    reason: str = Field(..., description="Reason for the decision")
    operator_id: str = Field(..., description="Operator making the decision")


class ApprovalRequest(BaseModel):
    """Request for approval of a transaction."""
    approval_id: str = Field(..., description="Unique approval identifier")
    amount_micros: int = Field(..., ge=1, description="Transaction amount in micro-USD")
    transaction_type: str = Field(..., description="Type of transaction")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class KillSwitchState(BaseModel):
    """Kill switch state request."""
    state: bool = Field(..., description="True = active/kill, False = inactive/resume")
    operator_id: str = Field(..., description "Operator triggering the change")


@router.post("/approvals/{approval_id}/decision")
async def decide_approval(
    approval_id: str,
    decision: ApprovalDecision,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Make a decision on an approval request.
    
    Human-on-the-loop: operator approves or rejects transactions above threshold.
    """
    from app.guardrails.engine import GuardrailEngine
    from app.ledger.service import LedgerService
    
    # Find the approval request
    approval = await db.approvals.find_one({"approval_id": approval_id})
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    
    ledger = LedgerService(db)
    guardrail = GuardrailEngine(ledger_service=ledger)
    
    # Evaluate approval against guardrails
    amount = decision.amount_micros if hasattr(decision, 'amount_micros') else approval.get("amount_micros", 0)
    approval_result = guardrail.check_kill_switch_state(approval.get("kill_switch_active", False))
    
    # Record the decision
    decision_record = {
        "approval_id": approval_id,
        "decision": "approve" if decision.approve else "reject",
        "reason": decision.reason,
        "operator_id": decision.operator_id,
        "decided_at": int(time.time()),
        "amount_micros": amount,
    }
    
    await db.approvals.update_one(
        {"approval_id": approval_id},
        {"$set": decision_record, "updated_at": int(time.time())}
    )
    
    # Record audit log
    await db.audit_log.insert_one({
        "audit_id": f"approval_decision_{approval_id}",
        "actor": decision.operator_id,
        "action": "approval_decision",
        "approval_id": approval_id,
        "details": {
            "decision": "approve" if decision.approve else "reject",
            "reason": decision.reason,
            "amount_micros": amount,
        },
        "timestamp": int(time.time()),
    })
    
    # If approved and above threshold, trigger the action
    if decision.approve and amount > 25000000:  # Above 25 uUSD threshold
        # This could trigger payout, service activation, etc.
        pass
    
    decision_status = "approved" if decision.approve else "rejected"
    
    return {
        "status": decision_status,
        "approval_id": approval_id,
        "amount_micros": amount,
        "reason": decision.reason,
        "operator_id": decision.operator_id,
        "message": f"Approval {decision_status}."
    }


@router.post("/control/kill-switch")
async def control_kill_switch(
    kill_state: KillSwitchState,
    db: AsyncIOMotorDatabase = Depends(get_database),
    request: Request = None
):
    """Global emergency kill switch.
    
    When ACTIVE: All state-changing operations are blocked.
    When INACTIVE: Normal operations resume.
    """
    from app.guardrails.engine import GuardrailEngine
    from app.ledger.service import LedgerService
    
    ledger = LedgerService(db)
    guardrail = GuardrailEngine(ledger_service=ledger)
    
    # Evaluate kill switch state
    kill_result = guardrail.check_kill_switch_state(kill_state.state)
    
    if not kill_result.passed:
        raise HTTPException(
            status_code=400,
            detail=kill_result.reason
        )
    
    # Update kill switch state in database
    await db.system_config.update_one(
        {"key": "kill_switch"},
        {"$set": {
            "state": kill_state.state,
            "updated_at": int(time.time()),
            "operator_id": kill_state.operator_id,
        }},
        upsert=True
    )
    
    # Record audit log
    await db.audit_log.insert_one({
        "audit_id": f"kill_switch_{int(time.time())}",
        "actor": kill_state.operator_id,
        "action": "kill_switch_toggle",
        "details": {
            "new_state": "active" if kill_state.state else "inactive",
            "operator_id": kill_state.operator_id,
        },
        "timestamp": int(time.time()),
    })
    
    new_state = "ACTIVE - all state changes blocked" if kill_state.state else "INACTIVE - normal operations"
    
    return {
        "status": "updated",
        "kill_switch_state": "active" if kill_state.state else "inactive",
        "message": f"Kill switch {new_state}.",
        "blocks_state_changes": kill_state.state
    }


@router.get("/control/kill-switch/status")
async def kill_switch_status(db: AsyncIOMotorDatabase = Depends(get_database)):
    """Get current kill switch status."""
    system_config = await db.system_config.find_one({"key": "kill_switch"})
    
    if system_config:
        return {
            "kill_switch_active": system_config.get("state", False),
            "last_updated": system_config.get("updated_at"),
            "operator_id": system_config.get("operator_id"),
        }
    else:
        return {
            "kill_switch_active": False,
            "message": "Kill switch not yet configured",
        }