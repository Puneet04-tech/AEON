"""Trade endpoints: run a trade, inspect trades and negotiation transcripts."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from app.api.deps import mutate
from app.db.client import get_database
from app.security.input_guard import require_id
from app.security.sessions import Session, require_judge_or_operator, require_viewer
from app.services import forecasts, trades as trades_service
from app.services.pricing import JOB_UNITS

router = APIRouter(prefix="/api/v1/trades", tags=["trades"])

ALLOWED_JOBS = {"image_resize": 4_000_000, "matrix_multiply": 220}


class JobSpec(BaseModel):
    type: Literal["image_resize", "matrix_multiply"]
    size: int = Field(ge=1, le=4_000_000)
    params: dict = Field(default_factory=dict)
    deadline_s: int = Field(default=30, ge=5, le=300)

    @field_validator("size")
    @classmethod
    def size_within_job_limit(cls, value: int, info):
        job_type = (info.data or {}).get("type")
        if job_type and value > ALLOWED_JOBS[job_type]:
            raise ValueError(f"size exceeds the limit for {job_type}")
        return value


class TradeRequest(BaseModel):
    buyer_id: str
    seller_id: Optional[str] = None
    job: JobSpec
    quantity: int = Field(default=1, ge=1, le=20)
    has_approval: bool = False


@router.post("", status_code=status.HTTP_201_CREATED)
async def run_trade(body: TradeRequest, request: Request,
                   session: Session = Depends(require_judge_or_operator)):
    try:
        require_id(body.buyer_id, "buyer_id")
        if body.seller_id:
            require_id(body.seller_id, "seller_id")
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    async def handler() -> dict:
        db = get_database()
        energy = await forecasts.energy_factor_now(db)
        try:
            return await trades_service.run_trade(
                db, body.buyer_id, body.job.model_dump(), seller_id=body.seller_id,
                quantity=body.quantity, has_approval=body.has_approval,
                actor=session.role, energy=energy,
            )
        except ValueError as exc:
            code = str(exc)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, code)

    return await mutate(request, body.model_dump(), handler)


@router.get("")
async def list_trades(limit: int = 50, state: Optional[str] = None,
                      buyer_id: Optional[str] = None, seller_id: Optional[str] = None,
                      session: Session = Depends(require_viewer)):
    trades = await trades_service.list_trades(get_database(), limit=min(limit, 200),
                                              state=state, buyer_id=buyer_id, seller_id=seller_id)
    return {"trades": trades}


@router.get("/{trade_id}")
async def get_trade(trade_id: str, session: Session = Depends(require_viewer)):
    trade = await trades_service.get_trade(get_database(), trade_id)
    if not trade:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trade not found")
    trade["negotiation_transcript"] = await trades_service.negotiation_transcript(get_database(), trade_id)
    return trade


@router.get("/{trade_id}/negotiation")
async def negotiation(trade_id: str, session: Session = Depends(require_viewer)):
    transcript = await trades_service.negotiation_transcript(get_database(), trade_id)
    if not transcript:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no negotiation for this trade")
    return {"trade_id": trade_id, "rounds": transcript}
