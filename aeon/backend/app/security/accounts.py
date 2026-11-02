"""User accounts stored in MongoDB (Atlas or local).

Accounts live in the `users_accounts` collection with a bcrypt password hash.
Email is the unique key. Roles mirror the session roles so a signed-up user
receives a normal operator session on login.
"""
import re
import structlog

from app.security.sessions import hash_password

logger = structlog.get_logger()

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
MIN_PASSWORD_LENGTH = 8

COLLECTION = "users_accounts"


class AccountError(Exception):
    """Raised with a user-safe message when signup/login input is invalid."""

    def __init__(self, message: str, code: str = "account_error"):
        super().__init__(message)
        self.code = code


def validate(email: str, password: str) -> None:
    if not _EMAIL_RE.match(email or ""):
        raise AccountError("Enter a valid email address", code="invalid_email")
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AccountError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
            code="weak_password",
        )


async def create_account(db, email: str, password: str, role: str = "operator") -> dict:
    """Create an account. Raises AccountError('email_taken') on duplicates."""
    email = (email or "").strip().lower()
    validate(email, password)
    existing = await db[COLLECTION].find_one({"email": email})
    if existing:
        raise AccountError("An account with this email already exists", code="email_taken")
    doc = {
        "email": email,
        "password_hash": hash_password(password),
        "role": role if role in ("operator", "viewer") else "operator",
        "created_at": None,  # set by the caller if a clock is wanted
        "disabled": False,
    }
    from datetime import datetime, timezone

    doc["created_at"] = datetime.now(timezone.utc)
    await db[COLLECTION].insert_one(doc)
    logger.info("account_created", email=email, role=doc["role"])
    return doc


async def verify_credentials(db, email: str, password: str) -> dict:
    """Return the account document when credentials match, else raise."""
    import bcrypt

    email = (email or "").strip().lower()
    account = await db[COLLECTION].find_one({"email": email})
    # Constant-ish time: always run a hash check so missing accounts look the
    # same as wrong passwords.
    if not account:
        bcrypt.checkpw((password or "").encode(), bcrypt.hashpw(b"dummy", bcrypt.gensalt()))
        raise AccountError("Invalid email or password", code="bad_credentials")
    if account.get("disabled"):
        raise AccountError("This account has been disabled", code="account_disabled")
    if not bcrypt.checkpw((password or "").encode(), account["password_hash"].encode()):
        raise AccountError("Invalid email or password", code="bad_credentials")
    return account
