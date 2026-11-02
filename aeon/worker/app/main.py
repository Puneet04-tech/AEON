"""AEON worker service.

Executes real compute jobs for the clearing house and meters CPU-seconds. Every
request must carry a valid HMAC signature, a fresh timestamp and a single-use
nonce. A signed chaos switch makes the worker fail health checks so recovery can
be demonstrated for real.
"""
import json
import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Dict

import structlog
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app import jobs as job_runner
from app.metering import Meter
from app.settings import settings
from app.signing import check_signature, consume_nonce, reset_nonces

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
)
logger = structlog.get_logger()

app = FastAPI(title="AEON Worker", version="1.0.0")
state: Dict[str, object] = {
    "healthy": True,
    "jobs_executed": 0,
    "cpu_seconds": 0.0,
    "started_at": datetime.now(timezone.utc),
    "last_failure": None,
    "corrupt_results": False,
}


async def _verify(request: Request, body: bytes, path: str) -> None:
    ok, reason = check_signature(
        request.method, path,
        request.headers.get("x-aeon-timestamp", ""),
        request.headers.get("x-aeon-nonce", ""),
        body,
        request.headers.get("x-aeon-signature", ""),
    )
    if not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"signature rejected: {reason}")
    if not consume_nonce(request.headers.get("x-aeon-nonce", "")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "nonce replay rejected")


@app.get("/health")
async def health():
    healthy = bool(state["healthy"])
    return {
        "status": "ok" if healthy else "unhealthy",
        "healthy": healthy,
        "worker_id": settings.worker_id,
        "jobs_executed": state["jobs_executed"],
        "cpu_seconds": round(float(state["cpu_seconds"]), 4),
        "uptime_seconds": int((datetime.now(timezone.utc) - state["started_at"]).total_seconds()),
    }


@app.get("/metrics")
async def metrics():
    return {
        "worker_id": settings.worker_id,
        "jobs_executed": state["jobs_executed"],
        "cpu_seconds": round(float(state["cpu_seconds"]), 4),
        "healthy": bool(state["healthy"]),
        "max_image_pixels": settings.max_image_pixels,
        "max_matrix_n": settings.max_matrix_n,
    }


@app.post("/jobs")
async def run_job(request: Request):
    body = await request.body()
    await _verify(request, body, "/jobs")
    if not state["healthy"]:
        state["last_failure"] = datetime.now(timezone.utc).isoformat()
        return JSONResponse({"detail": "worker is in a forced failure state"}, status_code=503)

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid JSON")

    job_type = payload.get("type")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    if job_type == "image_resize":
        # the caller sends a job size; translate it into concrete dimensions
        params = {**params}
        if "width" not in params:
            size = int(payload.get("size", 640 * 480))
            params.setdefault("source_width", 1280)
            params.setdefault("source_height", max(1, min(1280, size // 1280 or 1)))
            params.setdefault("width", 320)
            params.setdefault("height", 240)
    if job_type == "matrix_multiply":
        params = {**params}
        params.setdefault("n", int(payload.get("size", 96)))

    started_at = datetime.now(timezone.utc)
    started_perf = time.perf_counter()
    input_digest = hashlib.sha256(body).hexdigest()
    meter = Meter()
    try:
        with meter.measure():
            result = job_runner.run_job(job_type, params)
    except job_runner.JobError as exc:
        logger.warning("job_rejected", code=exc.code, job_type=str(job_type))
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            {"code": exc.code, "message": str(exc)})

    state["jobs_executed"] = int(state["jobs_executed"]) + 1
    state["cpu_seconds"] = float(state["cpu_seconds"]) + meter.cpu_seconds
    checksum = job_runner.canonical_digest(result)
    if state["corrupt_results"]:
        result = {**result, "corrupted_demo": True}
    completed_at = datetime.now(timezone.utc)
    logger.info("job_done", job_id=payload.get("job_id"), job_type=job_type,
                cpu_seconds=meter.cpu_seconds, checksum=checksum[:16])
    return {
        "job_id": payload.get("job_id") or uuid.uuid4().hex,
        "worker_id": settings.worker_id,
        "status": "ok",
        "cpu_seconds": meter.cpu_seconds,
        "wall_seconds": meter.wall_seconds,
        "checksum": checksum,
        "result": result,
        "evidence": {
            "input_digest": input_digest,
            "output_digest": checksum,
            "runtime_version": "worker-1.0.0",
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "wall_ms": int((time.perf_counter() - started_perf) * 1000),
        },
    }


@app.post("/admin/chaos")
async def chaos(request: Request):
    body = await request.body()
    await _verify(request, body, "/admin/chaos")
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid JSON")
    state["healthy"] = not bool(payload.get("fail"))
    state["corrupt_results"] = bool(payload.get("corrupt"))
    logger.warning("chaos_toggled", healthy=state["healthy"], corrupt=state["corrupt_results"])
    return {"worker_id": settings.worker_id, "healthy": state["healthy"],
            "corrupt": state["corrupt_results"]}


@app.post("/admin/reset")
async def reset(request: Request):
    """Test helper: clear nonces and failure state."""
    state["healthy"] = True
    state["corrupt_results"] = False
    reset_nonces()
    return {"ok": True}
