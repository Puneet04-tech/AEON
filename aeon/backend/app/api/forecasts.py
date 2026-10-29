"""Forecast and capacity-reservation endpoints (F8)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.deps import mutate
from app.db.client import get_database
from app.security.sessions import Session, require_judge_or_operator, require_operator, require_viewer
from app.services import forecasts, reservations

router = APIRouter(prefix="/api/v1", tags=["forecasts"])


class ReservationRequest(BaseModel):
    buyer_id: str = Field(min_length=3, max_length=64)
    provider_id: str = Field(min_length=3, max_length=64)
    cpu_seconds: int = Field(ge=10, le=3600)
    region_label: Optional[str] = Field(default=None, max_length=120)


class ResaleRequest(BaseModel):
    buyer_id: str = Field(min_length=3, max_length=64)
    ask_micro: Optional[int] = Field(default=None, ge=1, le=10**12)


@router.get("/forecasts")
async def forecast(session: Session = Depends(require_viewer)):
    db = get_database()
    current = await forecasts.get_forecast(db)
    return {
        "current": current,
        "regions": await forecasts.region_outlook(db),
        "disclaimer": "Weather is real (Open-Meteo). The energy price factor and regions are simulated.",
    }


@router.get("/reservations")
async def list_reservations(session: Session = Depends(require_viewer)):
    return {"reservations": await reservations.list_reservations(get_database())}


@router.post("/reservations", status_code=status.HTTP_201_CREATED)
async def create_reservation(body: ReservationRequest, request: Request,
                             session: Session = Depends(require_judge_or_operator)):
    async def handler() -> dict:
        try:
            return await reservations.create_reservation(get_database(), body.buyer_id,
                                                         body.provider_id, body.cpu_seconds,
                                                         body.region_label)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    return await mutate(request, body.model_dump(), handler)


@router.post("/reservations/{reservation_id}/resell")
async def resell(reservation_id: str, body: ResaleRequest, request: Request,
                 session: Session = Depends(require_judge_or_operator)):
    async def handler() -> dict:
        try:
            return await reservations.resell(get_database(), reservation_id, body.buyer_id,
                                             body.ask_micro)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    return await mutate(request, {"reservation_id": reservation_id, **body.model_dump()}, handler)


@router.post("/reservations/{reservation_id}/release")
async def release(reservation_id: str, request: Request,
                  session: Session = Depends(require_operator)):
    async def handler() -> dict:
        try:
            return await reservations.release(get_database(), reservation_id, actor="operator")
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    return await mutate(request, {"reservation_id": reservation_id}, handler)
