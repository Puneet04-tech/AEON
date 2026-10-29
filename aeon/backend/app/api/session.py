"""Session endpoints: operator login and metered judge access."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.deps import request_context
from app.db.client import get_database
from app.security.sessions import (
    Session,
    consume_scenario_quota,
    current_session,
    issue_session,
    operator_login_configured,
    require_operator,
    revoke_session,
    verify_operator_password,
)
from app.services import audit
from app.settings import settings

router = APIRouter(prefix="/api/v1/session", tags=["session"])


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class JudgeRequest(BaseModel):
    passphrase: Optional[str] = Field(default=None, max_length=200)


@router.post("/login")
async def login(body: LoginRequest, request: Request):
    if not operator_login_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Operator login is not configured (set OPERATOR_PASSWORD_HASH)")
    if not verify_operator_password(body.password):
        context = request_context(request)
        await audit.record(get_database(), actor_type="anonymous", actor_id="login",
                           action="session.login_failed", subject_type="session", subject_id="",
                           severity="warning", ip_hash=context["ip_hash"])
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid operator password")
    token, session = await issue_session(get_database(), "operator", 12 * 60)
    return {"token": token, "role": session.role, "expires_at": session.expires_at}


@router.post("/judge")
async def judge_session(request: Request):
    """Start a limited, metered judge session. No password: quotas do the work."""
    token, session = await issue_session(get_database(), "judge",
                                         settings.JUDGE_SESSION_MINUTES,
                                         request_context(request)["ip_hash"])
    await audit.record(get_database(), actor_type="judge", actor_id="judge",
                       action="session.judge_started", subject_type="session",
                       subject_id=session.jti, ip_hash=request_context(request)["ip_hash"])
    return {"token": token, "role": "judge", "expires_at": session.expires_at,
            "quotas": session.quotas,
            "note": "Judge mode runs the guided scenarios only. PayPal is sandbox."}


@router.get("/me")
async def me(session: Session = Depends(current_session)):
    return {"role": session.role, "jti": session.jti, "expires_at": session.expires_at,
            "quotas": session.quotas}


@router.post("/logout")
async def logout(session: Session = Depends(current_session)):
    await revoke_session(get_database(), session.jti)
    return {"ok": True}


@router.post("/quota")
async def spend_quota(session: Session = Depends(current_session)):
    """Internal helper so the UI can show remaining judge runs."""
    if session.role != "judge":
        return {"quotas": session.quotas}
    ok = await consume_scenario_quota(get_database(), session)
    return {"ok": ok}
