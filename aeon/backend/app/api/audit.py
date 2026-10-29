"""Read-only audit trail."""
from typing import Optional

from fastapi import APIRouter, Depends

from app.db.client import get_database
from app.security.sessions import Session, require_viewer

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("")
async def list_audit(limit: int = 100, action: Optional[str] = None,
                     session: Session = Depends(require_viewer)):
    query = {"action": action} if action else {}
    cursor = get_database().audit_log.find(query, {"_id": 0}).sort("at", -1).limit(min(limit, 500))
    return {"audit": [doc async for doc in cursor]}
