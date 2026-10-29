"""Append-only audit log. Every state change writes exactly one entry."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


def _hash(payload: Any) -> str:
    if payload is None:
        return ""
    try:
        blob = json.dumps(payload, default=str, sort_keys=True)
    except TypeError:  # pragma: no cover - defensive
        blob = str(payload)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


async def record(db, *, actor_type: str, actor_id: str, action: str, subject_type: str,
                 subject_id: str, before: Optional[dict] = None, after: Optional[dict] = None,
                 severity: str = "info", request_id: str = "", ip_hash: str = "",
                 detail: Optional[dict] = None) -> str:
    import uuid

    audit_id = f"aud_{uuid.uuid4().hex[:20]}"
    doc = {
        "id": audit_id,
        "at": datetime.now(timezone.utc),
        "actor": {"type": actor_type, "id": actor_id},
        "action": action,
        "subject": {"type": subject_type, "id": subject_id},
        "before_hash": _hash(before),
        "after_hash": _hash(after),
        "severity": severity,
        "ip_hash": ip_hash,
        "request_id": request_id,
        "detail": detail or {},
    }
    await db.audit_log.insert_one(doc)
    return audit_id


def hash_ip(ip: str) -> str:
    return hashlib.sha256((ip or "").encode()).hexdigest()[:16]
