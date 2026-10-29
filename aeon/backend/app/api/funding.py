"""Funding endpoints: create a PayPal order and capture it into the ledger."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.deps import mutate
from app.db.client import get_database
from app.paypal.client import PayPalError
from app.security.sessions import Session, require_operator, require_viewer
from app.services import funding as funding_service

router = APIRouter(prefix="/api/v1/funding", tags=["funding"])


class FundingRequest(BaseModel):
    agent_id: str = Field(min_length=3, max_length=64)
    amount_micro: int = Field(ge=1, le=50_000_000)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_funding(body: FundingRequest, request: Request,
                         session: Session = Depends(require_operator)):
    async def handler() -> dict:
        try:
            return await funding_service.create_funding(get_database(), body.agent_id,
                                                        body.amount_micro, actor="operator")
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
        except PayPalError as exc:
            raise HTTPException(exc.status, {"code": exc.code, "message": str(exc)})

    return await mutate(request, body.model_dump(), handler)


@router.post("/{funding_id}/capture")
async def capture_funding(funding_id: str, request: Request,
                          session: Session = Depends(require_operator)):
    async def handler() -> dict:
        try:
            return await funding_service.capture_funding(get_database(), funding_id, actor="operator")
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
        except PayPalError as exc:
            raise HTTPException(exc.status, {"code": exc.code, "message": str(exc)})

    return await mutate(request, {"funding_id": funding_id}, handler)


@router.get("")
async def list_funding(session: Session = Depends(require_viewer)):
    return {"funding": await funding_service.list_funding(get_database())}
