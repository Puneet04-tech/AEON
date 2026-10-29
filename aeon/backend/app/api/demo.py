"""Demo lifecycle: reset to a clean, funded set of agents for repeatable judging."""
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import mutate, request_context
from app.db.client import get_database
from app.db.seed import seed
from app.security.sessions import Session, require_operator
from app.services import audit, events

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


@router.post("/reset")
async def reset_demo(request: Request, session: Session = Depends(require_operator)):
    """Wipe trade/payment state and reseed the five demo agents.

    Destructive by design, operator-only, and refused while the kill switch is
    armed so it cannot race a live batch.
    """

    async def handler() -> dict:
        db = get_database()
        doc = await db.kv.find_one({"key": "kill_switch"})
        if (doc or {}).get("value", {}).get("active"):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "disarm the kill switch before resetting the demo")
        result = await seed(db, reset=True)
        await events.emit(db, "demo.reset", {"agents": result["agents"]}, actor="operator")
        await audit.record(db, actor_type="operator", actor_id="operator", action="demo.reset",
                           subject_type="system", subject_id="demo", severity="warning",
                           ip_hash=request_context(request)["ip_hash"])
        return {"ok": True, **result}

    return await mutate(request, {"action": "reset"}, handler)
