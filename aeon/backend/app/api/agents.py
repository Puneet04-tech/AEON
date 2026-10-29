"""
AEON Agents API Router

Handles agent registration, policy editing, pause/resume, and status queries.
Follows AEON blueprint Day 3: Agents, negotiation and real jobs.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
import structlog

from app.db.client import get_database
from app.ledger.service import LedgerService
from app.guardrails.engine import GuardrailEngine
from app.security.sessions import validate_role, validate_actor_for_resource

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["agents"])


# Pydantic models for agent data
class AgentPolicy(BaseModel):
    """Policy constraints for an agent."""
    max_budget_micros: int
    max_trades_per_hour: int = 50
    max_trades_per_day: int = 500
    allowed_regions: Optional[List[str]] = None
    allowed_counterparties: Optional[List[str]] = None
    requires_approval_above_micros: int = 25000000  # 25 uUSD
    
    @validator("max_budget_micros")
    def budget_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("max_budget_micros must be positive")
        return v


class AgentRegistration(BaseModel):
    """Agent registration request."""
    agent_id: str = Field(..., description="Unique agent identifier")
    role: str = Field(..., description="consumer or provider")
    profile: str = Field(..., description="Capacity profile label")
    paypal_email: str = Field(..., description="PayPal sandbox email")
    policy: AgentPolicy
    
    @validator("role")
    def role_must_be_valid(cls, v):
        if v not in ("consumer", "provider"):
            raise ValueError("role must be consumer or provider")
        return v
    
    @validator("agent_id")
    def agent_id_format(cls, v):
        from app.security.input_guard import validate_agent_id
        if not validate_agent_id(v):
            raise ValueError("invalid agent_id format")
        return v


class AgentPauseRequest(BaseModel):
    """Request to pause/resume an agent."""
    pause: bool = Field(..., description="True to pause, False to resume")
    reason: Optional[str] = Field(None, description="Optional pause reason")


class AgentStatusResponse(BaseModel):
    """Agent status response."""
    agent_id: str
    role: str
    status: str  # active, paused, suspended, faulted
    balance_micros: int
    bond_micros: int
    uptime_percent: float
    last_seen: Optional[int] = None


@router.post("/agents", status_code=201)
async def register_agent(
    agent_data: AgentRegistration,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Register a new agent with policy.
    
    Day 3: Agent models and registry endpoints.
    """
    from app.ledger.service import LedgerService
    
    ledger = LedgerService(db)
    guardrail = GuardrailEngine(
        ledger_service=ledger,
        agent_budgets={agent_data.agent_id: agent_data.policy.max_budget_micros},
        allowed_counterparties=agent_data.policy.allowed_counterparties,
    )
    
    # Validate role for registration
    if not validate_role(agent_data.role):
        raise HTTPException(status_code=400, detail="Invalid agent role")
    
    # Check for duplicate registration
    existing = await db.agents.find_one({"agent_id": agent_data.agent_id})
    if existing:
        raise HTTPException(status_code=409, detail="Agent already registered")
    
    # Create agent record
    agent_record = {
        "agent_id": agent_data.agent_id,
        "role": agent_data.role,
        "profile": agent_data.profile,
        "paypal_email": agent_data.paypal_email,
        "policy": agent_data.policy.dict(),
        "status": "active",
        "balance_micros": 0,
        "bond_micros": 0,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }
    
    await db.agents.insert_one(agent_record)
    
    # Initialize budget rule
    guardrail.budget_rules[agent_data.agent_id] = BudgetCapRule(
        budget_micros=agent_data.policy.max_budget_micros
    )
    
    logger.info("Agent registered", agent_id=agent_data.agent_id, role=agent_data.role)
    
    return {
        "status": "registered",
        "agent_id": agent_data.agent_id,
        "message": "Agent successfully registered in the AEON network"
    }


@router.get("/agents/{agent_id}", response_model=AgentStatusResponse)
async def get_agent_status(
    agent_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Get agent status and balance.
    
    Day 3: Agent registry and policy endpoints.
    """
    from app.security.input_guard import validate_agent_id
    
    if not validate_agent_id(agent_id):
        raise HTTPException(status_code=400, detail="Invalid agent ID format")
    
    agent = await db.agents.find_one({"agent_id": agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return AgentStatusResponse(
        agent_id=agent["agent_id"],
        role=agent["role"],
        status=agent["status"],
        balance_micros=agent.get("balance_micros", 0),
        bond_micros=agent.get("bond_micros", 0),
        uptime_percent=agent.get("uptime_percent", 100.0),
        last_seen=agent.get("last_seen"),
    )


@router.patch("/agents/{agent_id}/policy")
async def update_agent_policy(
    agent_id: str,
    new_policy: AgentPolicy,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Update agent policy.
    
    Day 3: Edit policy (operator).
    """
    from app.security.input_guard import validate_agent_id
    
    if not validate_agent_id(agent_id):
        raise HTTPException(status_code=400, detail="Invalid agent ID")
    
    # Check operator privileges (would require auth in production)
    # For now, allow update with simple check
    agent = await db.agents.find_one({"agent_id": agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Update policy
    await db.agents.update_one(
        {"agent_id": agent_id},
        {"$set": {"policy": new_policy.dict(), "updated_at": int(time.time())}}
    )
    
    logger.info("Agent policy updated", agent_id=agent_id)
    
    return {
        "status": "updated",
        "agent_id": agent_id,
        "message": "Agent policy successfully updated"
    }


@router.patch("/agents/{agent_id}/pause")
async def pause_agent(
    agent_id: str,
    pause_request: AgentPauseRequest,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Pause or resume an agent.
    
    Day 3: Pause and resume agent.
    """
    from app.security.input_guard import validate_agent_id
    
    if not validate_agent_id(agent_id):
        raise HTTPException(status_code=400, detail="Invalid agent ID")
    
    agent = await db.agents.find_one({"agent_id": agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Update status
    await db.agents.update_one(
        {"agent_id": agent_id},
        {"$set": {"status": "paused" if pause_request.pause else "active", 
                  "updated_at": int(time.time())}}
    )
    
    logger.info("Agent pause updated", agent_id=agent_id, paused=pause_request.pause)
    
    return {
        "status": "updated",
        "agent_id": agent_id,
        "paused": pause_request.pause,
        "message": f"Agent {'paused' if pause_request.pause else 'resumed'} successfully"
    }


@router.get("/agents", response_model=Dict[str, AgentStatusResponse])
async list_agents(
    db: AsyncIOMotorDatabase = Depends(get_database),
    role_filter: Optional[str] = None,
):
    """List all agents, optionally filtered by role.
    
    Day 3: Agent registry listing.
    """
    from app.security.input_guard import validate_role
    
    filter_dict = {}
    if role_filter:
        if not validate_role(role_filter):
            raise HTTPException(status_code=400, detail="Invalid role filter")
        filter_dict["role"] = role_filter
    
    cursor = db.agents.find(filter_dict)
    agents = await cursor.to_list(length=None)
    
    result = {}
    for agent in agents:
        result[agent["agent_id"]] = AgentStatusResponse(
            agent_id=agent["agent_id"],
            role=agent["role"],
            status=agent["status"],
            balance_micros=agent.get("balance_micros", 0),
            bond_micros=agent.get("bond_micros", 0),
            uptime_percent=agent.get("uptime_percent", 100.0),
            last_seen=agent.get("last_seen"),
        )
    
    return result