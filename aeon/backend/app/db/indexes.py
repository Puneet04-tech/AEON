"""Collection indexes, matching the access patterns used by the API.

Indexes are created on startup (idempotent) and by `python -m app.db.indexes`.
"""
import structlog
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import OperationFailure

logger = structlog.get_logger()

INDEXES = [
    ("agents", [("id", ASCENDING)], {"unique": True}),
    ("agents", [("paypal_email", ASCENDING)], {"unique": True}),
    ("agents", [("role", ASCENDING), ("status", ASCENDING)], {}),
    ("agents", [("region_label", ASCENDING)], {}),

    ("wallets", [("agent_id", ASCENDING)], {"unique": True}),

    ("ledger_entries", [("id", ASCENDING)], {"unique": True}),
    ("ledger_entries", [("txn_idem", ASCENDING)], {}),
    ("ledger_txns", [("posted_at", DESCENDING)], {}),
    ("ledger_entries", [("agent_id", ASCENDING), ("posted_at", DESCENDING)], {}),
    ("ledger_entries", [("txn_id", ASCENDING)], {}),
    ("ledger_entries", [("posted_at", DESCENDING)], {}),

    ("trades", [("id", ASCENDING)], {"unique": True}),
    ("trades", [("state", ASCENDING), ("updated_at", DESCENDING)], {}),
    ("trades", [("buyer_id", ASCENDING)], {}),
    ("trades", [("seller_id", ASCENDING)], {}),
    ("trades", [("job_id", ASCENDING)], {}),
    ("trades", [("created_at", DESCENDING)], {}),
    ("trades", [("seller_id", ASCENDING), ("state", ASCENDING), ("updated_at", DESCENDING)], {}),

    ("negotiations", [("trade_id", ASCENDING), ("round", ASCENDING)], {}),

    ("jobs", [("job_id", ASCENDING)], {"unique": True}),
    ("jobs", [("trade_id", ASCENDING)], {}),
    ("jobs", [("worker_id", ASCENDING), ("created_at", DESCENDING)], {}),

    ("execution_evidence", [("trade_id", ASCENDING)], {"unique": True}),
    ("verifications", [("trade_id", ASCENDING), ("created_at", DESCENDING)], {}),
    ("disputes", [("trade_id", ASCENDING)], {"unique": True}),
    ("disputes", [("state", ASCENDING), ("created_at", DESCENDING)], {}),

    ("funding_requests", [("id", ASCENDING)], {"unique": True}),
    ("funding_requests", [("paypal_order_id", ASCENDING)], {"sparse": True}),
    ("funding_requests", [("agent_id", ASCENDING), ("created_at", DESCENDING)], {}),

    ("settlements", [("id", ASCENDING)], {"unique": True}),
    ("settlements", [("sender_batch_id", ASCENDING)], {"unique": True}),
    ("settlements", [("state", ASCENDING)], {}),

    ("payout_items", [("id", ASCENDING)], {"unique": True}),
    ("payout_items", [("sender_item_id", ASCENDING)], {"unique": True}),
    ("payout_items", [("settlement_id", ASCENDING)], {}),
    ("payout_items", [("agent_id", ASCENDING)], {}),
    ("payout_items", [("paypal_item_id", ASCENDING)], {"sparse": True}),

    ("approvals", [("id", ASCENDING)], {"unique": True}),
    ("approvals", [("state", ASCENDING), ("created_at", DESCENDING)], {}),
    ("approvals", [("kind", ASCENDING)], {}),

    ("audit_log", [("id", ASCENDING)], {"unique": True}),
    ("audit_log", [("at", DESCENDING)], {}),
    ("audit_log", [("action", ASCENDING)], {}),
    ("audit_log", [("subject.id", ASCENDING), ("at", DESCENDING)], {}),

    ("idempotency_keys", [("key", ASCENDING)], {"unique": True}),
    ("idempotency_keys", [("expires_at", ASCENDING)], {"expireAfterSeconds": 0}),

    ("nonces", [("nonce", ASCENDING)], {"unique": True}),
    ("nonces", [("expires_at", ASCENDING)], {"expireAfterSeconds": 0}),

    ("llm_cache", [("key_hash", ASCENDING)], {"unique": True}),

    ("loans", [("id", ASCENDING)], {"unique": True}),
    ("loans", [("borrower_id", ASCENDING), ("state", ASCENDING)], {}),

    ("reservations", [("id", ASCENDING)], {"unique": True}),
    ("reservations", [("buyer_id", ASCENDING)], {}),

    ("forecasts", [("region_label", ASCENDING)], {"unique": True}),

    ("webhook_events", [("event_id", ASCENDING)], {"unique": True}),

    ("scenario_runs", [("run_id", ASCENDING)], {"unique": True}),
    ("scenario_runs", [("scenario", ASCENDING), ("started_at", DESCENDING)], {}),

    ("events", [("seq", ASCENDING)], {"unique": True}),
    ("events", [("created_at", DESCENDING)], {}),

    ("users_sessions", [("jti", ASCENDING)], {"unique": True}),
    ("users_sessions", [("expires_at", ASCENDING)], {"expireAfterSeconds": 0}),

    ("users_accounts", [("email", ASCENDING)], {"unique": True}),

    ("kv", [("key", ASCENDING)], {"unique": True}),
]


async def create_indexes(db) -> int:
    created = 0
    for collection, keys, options in INDEXES:
        try:
            await db[collection].create_index(keys, **options)
            created += 1
        except OperationFailure as exc:  # pragma: no cover - depends on cluster state
            logger.warning("index_create_failed", collection=collection, error=str(exc))
    logger.info("indexes_ready", count=created)
    return created


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    from app.db.client import connect_to_mongo, get_database

    async def main() -> None:
        await connect_to_mongo()
        await create_indexes(get_database())

    asyncio.run(main())
