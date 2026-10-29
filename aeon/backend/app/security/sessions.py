"""Operator and judge sessions.

Tokens are HS256 JWTs signed with SESSION_SECRET. The server keeps the session
row (role, expiry, scenario quota) so a token can be revoked and so judge mode
can be metered.
"""
import hmac
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Optional

import jwt
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.settings import settings

logger = structlog.get_logger()

ROLES = ("operator", "judge", "viewer")
_HS256 = "HS256"
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class Session:
    jti: str
    role: str
    expires_at: int
    quotas: Dict[str, int]

    @property
    def is_operator(self) -> bool:
        return self.role == "operator"


def _now() -> int:
    return int(time.time())


def create_token(jti: str, role: str, minutes: int) -> str:
    now = _now()
    payload = {
        "sub": role,
        "role": role,
        "jti": jti,
        "iat": now,
        "nbf": now,
        "exp": now + minutes * 60,
        "iss": "aeon",
    }
    return jwt.encode(payload, settings.SESSION_SECRET, algorithm=_HS256)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SESSION_SECRET, algorithms=[_HS256], issuer="aeon")


def verify_operator_password(password: str) -> bool:
    """Check the operator password against the configured hash / dev fallback."""
    if settings.OPERATOR_PASSWORD_HASH:
        try:
            import bcrypt

            return bcrypt.checkpw(password.encode(), settings.OPERATOR_PASSWORD_HASH.encode())
        except Exception:  # malformed hash must not authenticate anybody
            logger.error("operator_hash_invalid")
            return False
    if settings.OPERATOR_PASSWORD:
        return hmac.compare_digest(password, settings.OPERATOR_PASSWORD)
    return False


def operator_login_configured() -> bool:
    return bool(settings.OPERATOR_PASSWORD_HASH or settings.OPERATOR_PASSWORD)


async def issue_session(db, role: str, minutes: int, ip_hash: str = "") -> tuple[str, Session]:
    if role not in ROLES:
        raise ValueError(f"unknown role {role}")
    jti = uuid.uuid4().hex
    expires_at = _now() + minutes * 60
    quotas = {"scenarios_left": settings.JUDGE_SCENARIO_QUOTA if role == "judge" else -1}
    await db.users_sessions.insert_one({
        "id": jti,
        "jti": jti,
        "role": role,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.fromtimestamp(expires_at, timezone.utc),
        "ip_hash": ip_hash,
        "quotas": quotas,
        "revoked": False,
    })
    token = create_token(jti, role, minutes)
    return token, Session(jti=jti, role=role, expires_at=expires_at, quotas=quotas)


async def revoke_session(db, jti: str) -> None:
    await db.users_sessions.update_one({"jti": jti}, {"$set": {"revoked": True}})


async def consume_scenario_quota(db, session: Session) -> bool:
    """Atomically decrement a judge's scenario quota. Operators are unmetered."""
    if session.role != "judge":
        return True
    result = await db.users_sessions.update_one(
        {"jti": session.jti, "quotas.scenarios_left": {"$gt": 0}, "revoked": {"$ne": True}},
        {"$inc": {"quotas.scenarios_left": -1}},
    )
    return result.modified_count == 1


async def load_session(db, token: str) -> Session:
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session token")

    row = await db.users_sessions.find_one({"jti": payload.get("jti")})
    if not row or row.get("revoked"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session revoked")
    stored_expiry = row["expires_at"]
    if hasattr(stored_expiry, "timestamp"):
        if stored_expiry.tzinfo is None:  # some drivers return naive UTC datetimes
            stored_expiry = stored_expiry.replace(tzinfo=timezone.utc)
        expires_at = int(stored_expiry.timestamp())
    else:
        expires_at = int(stored_expiry)
    if expires_at < _now():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    return Session(jti=row["jti"], role=row["role"], expires_at=expires_at,
                   quotas=row.get("quotas", {}))


def extract_token(request: Request,
                  credentials: Optional[HTTPAuthorizationCredentials] = None) -> str:
    token = credentials.credentials if credentials else ""
    if not token:
        # EventSource cannot set headers; SSE clients may pass ?token=
        token = request.query_params.get("token", "")
    return token


async def session_from_request(request: Request, token: str = "") -> Session:
    """Resolve a session outside FastAPI's dependency injection (SSE routes)."""
    token = token or extract_token(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing session token")
    from app.db.client import get_database

    return await load_session(get_database(), token)


async def current_session(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Session:
    return await session_from_request(request, extract_token(request, credentials))


def require_role(*roles: Iterable[str]):
    allowed = set(roles)

    async def dependency(session: Session = Depends(current_session)) -> Session:
        if session.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role: {sorted(allowed)}")
        return session

    return dependency


require_operator = require_role("operator")
require_viewer = require_role("operator", "viewer", "judge")
require_judge_or_operator = require_role("operator", "judge")


def hash_password(password: str) -> str:
    import bcrypt

    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
