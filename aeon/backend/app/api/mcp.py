"""MCP endpoint (JSON-RPC 2.0) plus a human-readable tool catalogue."""
from typing import Any, Dict, List, Union

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.db.client import get_database
from app.mcp import server as mcp_server
from app.security.sessions import Session, current_session, require_viewer
from app.services import audit, treasurer

router = APIRouter(tags=["mcp"])


@router.get("/api/v1/mcp/tools")
async def tool_catalogue(session: Session = Depends(require_viewer)):
    return {
        "server": mcp_server.SERVER_INFO,
        "protocol_version": mcp_server.PROTOCOL_VERSION,
        "endpoint": "POST /mcp",
        "tools": mcp_server.TOOLS,
        "note": "Every tool is read-only or proposing; nothing here moves money.",
    }


@router.get("/api/v1/payments/overview")
async def payments_overview(session: Session = Depends(require_viewer)):
    return await treasurer.payments_overview(get_database())


@router.get("/api/v1/treasurer/plan")
async def treasurer_plan(session: Session = Depends(require_viewer)):
    return await treasurer.propose_batch_plan(get_database())


@router.get("/api/v1/treasurer/orders")
async def treasurer_orders(limit: int = 20, session: Session = Depends(require_viewer)):
    return {"orders": await treasurer.list_orders(get_database(), min(limit, 50))}


@router.get("/api/v1/treasurer/transactions")
async def treasurer_transactions(limit: int = 40, session: Session = Depends(require_viewer)):
    return {"transactions": await treasurer.list_transactions(get_database(), min(limit, 100))}


@router.post("/mcp")
async def mcp_endpoint(request: Request, session: Session = Depends(current_session)):
    """JSON-RPC entry point. A single object or a batch array is accepted."""
    try:
        payload: Union[Dict[str, Any], List[Dict[str, Any]]] = await request.json()
    except ValueError:
        return JSONResponse({"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": "parse error"}},
                            status_code=status.HTTP_400_BAD_REQUEST)

    db = get_database()
    if isinstance(payload, list):
        if not payload:
            return JSONResponse({"jsonrpc": "2.0", "id": None,
                                 "error": {"code": -32600, "message": "empty batch"}},
                                status_code=status.HTTP_400_BAD_REQUEST)
        responses = [await mcp_server.handle(db, item) for item in payload if isinstance(item, dict)]
        await audit.record(db, actor_type="agent", actor_id=session.role, action="mcp.batch",
                           subject_type="mcp", subject_id=str(len(responses)))
        return responses

    response = await mcp_server.handle(db, payload)
    method = payload.get("method", "") if isinstance(payload, dict) else ""
    await audit.record(db, actor_type="agent", actor_id=session.role, action=f"mcp.{method or 'call'}",
                       subject_type="mcp", subject_id=str(method)[:80],
                       severity="error" if "error" in response else "info")
    return response
