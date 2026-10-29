"""Agent registry and policy endpoints."""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import mutate, request_context
from app.db.client import get_database
from app.ledger.service import AGENT_AVAILABLE, LedgerService
from app.security.sessions import Session, require_operator, require_viewer
from app.services import audit, events

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

ROLES = {"consumer", "provider", "treasurer", "lender"}
STATUSES = {"ACTIVE", "PAUSED", "SUSPENDED"}


class Policy(BaseModel):
    per_trade_cap_micro: int = Field(default=5_000_000, ge=0, le=10**12)
    daily_cap_micro: int = Field(default=20_000_000, ge=0, le=10**12)
    price_band_bps: int = Field(default=2500, ge=0, le=9000)
    allowlist: List[str] = Field(default_factory=list)
    approval_threshold_micro: int = Field(default=25_000_000, ge=0)
    velocity_per_min: int = Field(default=12, ge=0, le=1000)
    cash_out: bool = False


class Profile(BaseModel):
    capacity_cpu_s_per_min: int = Field(default=0, ge=0)
    base_cost_micro: int = Field(default=4000, ge=1)
    worker_url: str = Field(default="", max_length=500)


class AgentCreate(BaseModel):
    id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    role: str
    region_label: str = Field(default="Region A (simulated)", max_length=120)
    paypal_email: EmailStr
    profile: Profile = Field(default_factory=Profile)
    policy: Policy = Field(default_factory=Policy)


class PolicyUpdate(BaseModel):
    per_trade_cap_micro: Optional[int] = Field(default=None, ge=0, le=10**12)
    daily_cap_micro: Optional[int] = Field(default=None, ge=0, le=10**12)
    price_band_bps: Optional[int] = Field(default=None, ge=0, le=9000)
    allowlist: Optional[List[str]] = None
    approval_threshold_micro: Optional[int] = Field(default=None, ge=0)
    velocity_per_min: Optional[int] = Field(default=None, ge=0, le=1000)
    cash_out: Optional[bool] = None


def _public(agent: dict) -> dict:
    return {k: v for k, v in agent.items() if k != "_id"}


@router.get("")
async def list_agents(session: Session = Depends(require_viewer)):
    cursor = get_database().agents.find({}, {"_id": 0}).sort("name", 1)
    agents = [agent async for agent in cursor]
    ledger = LedgerService(get_database())
    for agent in agents:
        agent["balances"] = await ledger.balances(agent["id"])
    return {"agents": agents}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent(body: AgentCreate, request: Request, _: Session = Depends(require_operator)):
    if body.role not in ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"role must be one of {sorted(ROLES)}")
    db = get_database()

    async def handler() -> dict:
        existing = await db.agents.find_one({"id": body.id})
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, "agent already exists")
        now = datetime.now(timezone.utc)
        doc = {
            "id": body.id,
            "name": body.name,
            "role": body.role,
            "status": "ACTIVE",
            "owner": "operator",
            "region_label": body.region_label,
            "paypal_email": str(body.paypal_email),
            "profile": body.profile.model_dump(),
            "policy": body.policy.model_dump(),
            "risk": {"uptime_30d": 1.0, "late_count": 0},
            "created_at": now,
            "updated_at": now,
        }
        await db.agents.insert_one({**doc})
        await LedgerService(db).wallet(body.id)
        await events.emit(db, "agent.created", {"agent_id": body.id, "role": body.role}, actor="operator")
        await audit.record(db, actor_type="operator", actor_id="operator", action="agent.created",
                           subject_type="agent", subject_id=body.id, after={"role": body.role},
                           **{k: v for k, v in request_context(request).items() if k == "ip_hash"})
        return _public(doc)

    return await mutate(request, body.model_dump(), handler)


@router.get("/{agent_id}")
async def get_agent(agent_id: str, session: Session = Depends(require_viewer)):
    db = get_database()
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
    ledger = LedgerService(db)
    agent["balances"] = await ledger.balances(agent_id)
    agent["statement"] = await ledger.statement(agent_id, limit=25)
    agent["loans"] = [loan async for loan in db.loans.find({"borrower_id": agent_id}, {"_id": 0})]
    return agent


@router.get("/{agent_id}/statement")
async def statement(agent_id: str, limit: int = 100, session: Session = Depends(require_viewer)):
    return {"entries": await LedgerService(get_database()).statement(agent_id, limit=min(limit, 500))}


@router.patch("/{agent_id}/policy")
async def update_policy(agent_id: str, body: PolicyUpdate, request: Request,
                        _: Session = Depends(require_operator)):
    db = get_database()

    async def handler() -> dict:
        agent = await db.agents.find_one({"id": agent_id})
        if not agent:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
        updates = {f"policy.{k}": v for k, v in body.model_dump(exclude_none=True).items()}
        if not updates:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "no policy fields supplied")
        await db.agents.update_one({"id": agent_id},
                                   {"$set": {**updates, "updated_at": datetime.now(timezone.utc)}})
        await audit.record(db, actor_type="operator", actor_id="operator", action="agent.policy_updated",
                           subject_type="agent", subject_id=agent_id,
                           before=agent.get("policy"), after=body.model_dump(exclude_none=True))
        return {"ok": True, "agent_id": agent_id, "policy": body.model_dump(exclude_none=True)}

    return await mutate(request, body.model_dump(), handler)


async def _set_status(agent_id: str, status_value: str, action: str) -> dict:
    if status_value not in STATUSES:
        raise ValueError("invalid_status")
    db = get_database()
    agent = await db.agents.find_one({"id": agent_id})
    if not agent:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
    await db.agents.update_one({"id": agent_id},
                               {"$set": {"status": status_value,
                                         "updated_at": datetime.now(timezone.utc)}})
    await events.emit(db, f"agent.{action}", {"agent_id": agent_id, "status": status_value},
                      actor="operator")
    await audit.record(db, actor_type="operator", actor_id="operator", action=f"agent.{action}",
                       subject_type="agent", subject_id=agent_id,
                       before={"status": agent.get("status")}, after={"status": status_value})
    return {"ok": True, "agent_id": agent_id, "status": status_value}


@router.post("/{agent_id}/pause")
async def pause_agent(agent_id: str, request: Request, _: Session = Depends(require_operator)):
    return await mutate(request, {"agent_id": agent_id}, lambda: _set_status(agent_id, "PAUSED", "paused"))


@router.post("/{agent_id}/resume")
async def resume_agent(agent_id: str, request: Request, _: Session = Depends(require_operator)):
    return await mutate(request, {"agent_id": agent_id}, lambda: _set_status(agent_id, "ACTIVE", "resumed"))


@router.get("/{agent_id}/funding")
async def agent_funding(agent_id: str, session: Session = Depends(require_viewer)):
    cursor = get_database().funding_requests.find({"agent_id": agent_id}, {"_id": 0}).sort("created_at", -1).limit(50)
    return {"funding": [doc async for doc in cursor]}
