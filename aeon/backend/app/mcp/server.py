"""Minimal MCP (Model Context Protocol) server for the treasurer agent.

Exposed over JSON-RPC 2.0 at `POST /mcp`, which is the shape an MCP client (the
PayPal Agent Toolkit host, Claude Desktop, or a custom agent) can call:

    initialize  -> protocol version and tool capability
    tools/list  -> read-only tools plus one proposing tool
    tools/call  -> dispatcher

Every tool is either read-only or *proposes* an action that still needs the
guardrail and human approval path. No tool can move money by itself.
"""
from typing import Any, Dict, List

import structlog

from app.ledger.service import LedgerService
from app.services import settlement, treasurer

logger = structlog.get_logger()

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "aeon-treasurer", "version": "1.0.0"}


def _schema(properties: Dict[str, Any], required: List[str] = None) -> Dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [],
            "additionalProperties": False}


TOOLS = [
    {
        "name": "aeon_list_orders",
        "description": "List PayPal funding orders with their capture state (sandbox only).",
        "inputSchema": _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 50}}),
    },
    {
        "name": "aeon_list_transactions",
        "description": "List money that actually moved: captures in and settled payouts out.",
        "inputSchema": _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 100}}),
    },
    {
        "name": "aeon_ledger_balances",
        "description": "Read agent wallets plus system account totals and the treasury float.",
        "inputSchema": _schema({}),
    },
    {
        "name": "aeon_invariant",
        "description": "Check the double-entry invariant: postings sum to zero and no wallet is negative.",
        "inputSchema": _schema({}),
    },
    {
        "name": "aeon_propose_settlement",
        "description": (
            "Propose the next netted payout batch with a treasurer rationale and the guardrail "
            "verdict. Read-only: submitting the batch still requires the operator endpoint or an "
            "approved approval record."
        ),
        "inputSchema": _schema({}),
    },
    {
        "name": "aeon_payment_overview",
        "description": "One call that returns PayPal mode, orders, transactions and past batches.",
        "inputSchema": _schema({}),
    },
]

TOOL_NAMES = {tool["name"] for tool in TOOLS}


class MCPError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


async def _call_tool(db, name: str, arguments: Dict[str, Any]) -> Any:
    limit = arguments.get("limit")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int)):
        raise MCPError(-32602, "limit must be an integer")
    limit = max(1, min(int(limit or 20), 100))

    if name == "aeon_list_orders":
        return await treasurer.list_orders(db, limit)
    if name == "aeon_list_transactions":
        return await treasurer.list_transactions(db, limit)
    if name == "aeon_ledger_balances":
        ledger = LedgerService(db)
        wallets = await ledger.all_balances()
        system = {}
        async for doc in db.account_totals.find({}, {"_id": 1, "amount_micro": 1}):
            system[doc["_id"]] = int(doc["amount_micro"])
        return {"agents": wallets, "system_accounts": system,
                "treasury_float_micro": await ledger.treasury_float_micro(),
                "treasury_funds_micro": await ledger.treasury_funds_micro()}
    if name == "aeon_invariant":
        return await LedgerService(db).invariant()
    if name == "aeon_propose_settlement":
        return await treasurer.propose_batch_plan(db)
    if name == "aeon_payment_overview":
        return await treasurer.payments_overview(db)
    raise MCPError(-32602, f"unknown tool: {name}")


async def _dispatch(db, method: str, params: Dict[str, Any]) -> Any:
    if method == "initialize":
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        }
    if method in {"tools/list", "mcp/tools/list"}:
        return {"tools": TOOLS}
    if method in {"tools/call", "mcp/tools/call"}:
        name = params.get("name")
        if name not in TOOL_NAMES:
            raise MCPError(-32602, f"unknown tool: {name}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise MCPError(-32602, "arguments must be an object")
        result = await _call_tool(db, name, arguments)
        return {"content": [{"type": "text", "text": _json(result)}], "isError": False}
    if method == "ping":
        return {}
    raise MCPError(-32601, f"method not found: {method}")


def _json(value: Any) -> str:
    import json

    return json.dumps(value, default=str)


async def handle(db, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle one JSON-RPC request object and return a JSON-RPC response."""
    request_id = payload.get("id")
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32600, "message": "invalid request"}}
    method = payload.get("method")
    params = payload.get("params") or {}
    if not isinstance(method, str) or not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32600, "message": "invalid request"}}
    try:
        result = await _dispatch(db, method, params)
    except MCPError as exc:
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": exc.code, "message": exc.message}}
    except Exception as exc:  # a tool failure must not take the server down
        logger.warning("mcp_tool_failed", method=method, error=str(exc)[:200])
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32603, "message": f"internal error: {str(exc)[:160]}"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


async def settlement_preview(db) -> Dict[str, Any]:
    """REST mirror of the propose tool, used by the console."""
    return await settlement.build_plan(db)
