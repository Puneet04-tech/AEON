import secrets
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import structlog
from passlib.context import CryptContext

logger = structlog.get_logger()

# Password hashing
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_session_id() -> str:
    """Generate a cryptographically secure session ID."""
    return secrets.token_urlsafe(32)


def create_session_token(user_id: str, expires_minutes: int = 30) -> str:
    """Create a signed session token for operator authentication."""
    issued_at = int(time.time())
    expires_at = issued_at + (expires_minutes * 60)
    payload = {
        "user_id": user_id,
        "iat": issued_at,
        "exp": expires_at,
        "type": "session",
    }
    return sign_payload(payload)


def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify a session token and return its payload if valid."""
    payload = verify_payload(token)
    if payload and payload.get("type") == "session":
        return payload
    return None


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return password_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return password_context.verify(plain_password, hashed_password)


def generate_operator_password_hash(password: str) -> str:
    """Generate a hashed password for the operator account."""
    return hash_password(password)


# Role-based access control
ALLOWED_ROLES = {"operator", "judge", "admin"}


def validate_role(role: str) -> bool:
    """Validate that a role is allowed."""
    return role in ALLOWED_ROLES


def validate_actor_for_resource(actor_role: str, resource_role: str) -> bool:
    """Check if an actor with actor_role can access resources with resource_role."""
    # Operators can access everything, judges can view, admins can modify
    role_hierarchy = {
        "operator": ["operator", "judge", "admin"],
        "judge": ["judge", "admin"],
        "admin": ["admin"],
    }
    return actor_role in role_hierarchy.get(resource_role, [])