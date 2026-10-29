"""MongoDB connection handling.

A single AsyncIOMotorClient is shared by the process. Tests replace `db` with a
mongomock-motor client through `set_database`, so the same code paths run in
tests and production.
"""
from typing import Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.settings import settings

logger = structlog.get_logger()

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


async def connect_to_mongo() -> None:
    global _client, _db
    if _db is not None:
        return
    _client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
    _db = _client[settings.MONGODB_DB]
    logger.info("mongo_connected", db=settings.MONGODB_DB)


async def close_mongo_connection() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


def set_database(database: AsyncIOMotorDatabase) -> None:
    """Inject a database (used by tests and by the test harness)."""
    global _db
    _db = database


def get_database() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not initialised; call connect_to_mongo() first")
    return _db
