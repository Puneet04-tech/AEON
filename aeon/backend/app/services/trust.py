"""Execution evidence, deterministic verification, and provider reputation."""
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.services.worker_client import canonical_digest


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_evidence(trade: dict, job: dict, envelope: dict, elapsed_ms: int) -> dict:
    result = envelope.get("result") or {}
    checksum = envelope.get("checksum") or canonical_digest(result)
    worker_id = str(envelope.get("worker_id") or "")
    evidence = envelope.get("evidence") or {}
    return {
        "id": f"evd_{uuid.uuid4().hex[:20]}",
        "trade_id": trade["id"],
        "job_id": trade["job_id"],
        "worker_id": worker_id,
        "job_type": job.get("type"),
        "input_digest": evidence.get("input_digest") or hashlib.sha256(
            canonical_digest({"type": job.get("type"), "size": job.get("size"),
                              "params": job.get("params", {})}).encode()
        ).hexdigest(),
        "output_digest": checksum,
        "checksum": checksum,
        "runtime_version": evidence.get("runtime_version", "worker-1.0.0"),
        "started_at": evidence.get("started_at"),
        "completed_at": evidence.get("completed_at"),
        "cpu_seconds": float(envelope.get("cpu_seconds", 0.0)),
        "wall_ms": elapsed_ms,
        "result_shape": {
            "keys": sorted(result.keys()),
            "kind": result.get("kind"),
        },
        "verification_level": "signed_execution",
        "created_at": _now(),
    }


def verify_evidence(evidence: dict, result: dict, level: str = "deterministic") -> dict:
    expected = canonical_digest(result)
    passed = expected == evidence.get("output_digest") == evidence.get("checksum")
    shape_kind = evidence.get("result_shape", {}).get("kind")
    if passed and level == "deterministic" and shape_kind is not None:
        passed = bool(shape_kind)
    return {
        "id": f"ver_{uuid.uuid4().hex[:20]}",
        "level": level,
        "passed": passed,
        "checks": [
            {"name": "output_checksum", "passed": expected == evidence.get("output_digest")},
            {"name": "envelope_checksum", "passed": expected == evidence.get("checksum")},
            {"name": "result_shape", "passed": shape_kind is None or bool(shape_kind)},
        ],
        "checked_at": _now(),
    }


async def provider_reputation(db, agent_id: str) -> dict:
    cursor = db.trades.find(
        {"seller_id": agent_id, "state": {"$in": ["SETTLED", "REFUNDED", "DISPUTED"]}},
        {"state": 1, "verification": 1, "failure": 1, "updated_at": 1},
    ).sort("updated_at", -1).limit(100)
    trades = [doc async for doc in cursor]
    total = len(trades)
    successful = sum(1 for trade in trades if trade.get("state") == "SETTLED")
    verified = sum(1 for trade in trades if (trade.get("verification") or {}).get("passed"))
    disputed = sum(1 for trade in trades if trade.get("state") in {"DISPUTED", "REFUNDED"})
    sample = max(total, 1)
    success_rate = successful / sample
    verification_rate = verified / sample
    dispute_rate = disputed / sample
    score = round(max(0.0, min(100.0, 100 * (
        0.55 * success_rate + 0.35 * verification_rate - 0.25 * dispute_rate
    ))), 2)
    return {
        "agent_id": agent_id,
        "score": score,
        "sample_size": total,
        "successful_trades": successful,
        "verified_trades": verified,
        "disputed_trades": disputed,
        "success_rate": round(success_rate, 4),
        "verification_rate": round(verification_rate, 4),
        "dispute_rate": round(dispute_rate, 4),
        "window": "last_100_trades",
        "updated_at": _now(),
    }


async def refresh_provider_reputation(db, agent_id: str) -> dict:
    reputation = await provider_reputation(db, agent_id)
    await db.agents.update_one(
        {"id": agent_id},
        {"$set": {"reputation": reputation, "updated_at": _now()}},
    )
    return reputation


async def selection_explanation(db, agent: dict, quote_micro: int) -> dict:
    reputation = agent.get("reputation") or await provider_reputation(db, agent["id"])
    return {
        "provider_id": agent["id"],
        "provider_name": agent.get("name", agent["id"]),
        "quote_micro": quote_micro,
        "reputation_score": reputation["score"],
        "sample_size": reputation["sample_size"],
        "verification_rate": reputation["verification_rate"],
        "reason": "eligible provider with lowest trust-adjusted quote",
    }
