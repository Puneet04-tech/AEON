"""Credit line endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.deps import mutate
from app.db.client import get_database
from app.security.sessions import Session, require_judge_or_operator, require_viewer
from app.services import loans

router = APIRouter(prefix="/api/v1/loans", tags=["loans"])


class LoanRequest(BaseModel):
    borrower_id: str = Field(min_length=3, max_length=64)
    amount_micro: int = Field(ge=100_000, le=20_000_000)
    lender_id: Optional[str] = Field(default=None, max_length=64)


@router.get("")
async def list_loans(session: Session = Depends(require_viewer)):
    return {"loans": await loans.list_loans(get_database())}


@router.post("/request", status_code=status.HTTP_201_CREATED)
async def request_loan(body: LoanRequest, request: Request,
                       session: Session = Depends(require_judge_or_operator)):
    async def handler() -> dict:
        try:
            return await loans.request_credit(get_database(), body.borrower_id,
                                              body.amount_micro, body.lender_id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    return await mutate(request, body.model_dump(), handler)
