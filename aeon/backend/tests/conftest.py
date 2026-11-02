"""Test harness: in-memory Mongo, an ASGI client and signed-in sessions.

The application code under test is exactly the production code path; only the
database and the outbound HTTP calls are replaced.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("LLM_MODE", "off")
os.environ.setdefault("PAYPAL_MODE", "mock")
os.environ.setdefault("AUTO_SEED", "false")
os.environ.setdefault("OPERATOR_PASSWORD", "test-operator-password")
os.environ.setdefault("RATE_LIMIT_MAX", "10000")
# Tests use the existing isolated adapter so they never contact PayPal. Product
# and deployment defaults remain sandbox-only with no simulated money movement.
os.environ.setdefault("PAYPAL_MODE", "mock")
os.environ.setdefault("ALLOW_MOCK_PAYPAL", "true")

from app.db.client import set_database  # noqa: E402
from app.db.indexes import create_indexes  # noqa: E402
from app.db.seed import seed  # noqa: E402
from app.ledger.service import LedgerService  # noqa: E402
from app.main import app  # noqa: E402
from app.security.sessions import issue_session  # noqa: E402


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient()
    database = client["aeon_test"]
    set_database(database)
    try:
        await create_indexes(database)
    except Exception:
        pass
    yield database
    client.close()
    set_database(None)  # type: ignore[arg-type]


@pytest_asyncio.fixture
async def seeded(db):
    await seed(db)
    return db


@pytest_asyncio.fixture
async def operator_token(db):
    token, _ = await issue_session(db, "operator", 60)
    return token


@pytest_asyncio.fixture
async def judge_token(db):
    token, _ = await issue_session(db, "judge", 30)
    return token


@pytest_asyncio.fixture
async def client(db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
def auth(operator_token):
    return {"Authorization": f"Bearer {operator_token}"}


@pytest_asyncio.fixture
async def ledger(db):
    return LedgerService(db)


def fake_dispatch(result=None, cpu_seconds=0.05, fail_code=None):
    """Build a dispatch_job replacement that returns a valid signed envelope."""
    from app.services.worker_client import WorkerError, canonical_digest

    async def _dispatch(db_, worker_url, job):
        if fail_code:
            raise WorkerError("forced failure", fail_code)
        payload = result if result is not None else {"echo": job["job_id"], "pixels": 307200}
        return {
            "job_id": job["job_id"],
            "worker_id": "worker-test",
            "status": "ok",
            "cpu_seconds": cpu_seconds,
            "checksum": canonical_digest(payload),
            "result": payload,
        }

    return _dispatch
