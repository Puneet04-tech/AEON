"""
MongoDB indexes for AEON collections
"""
from motor.motor_asyncio import AsyncIOMotorDatabase


async def create_indexes(db: AsyncIOMotorDatabase):
    # agents collection
    await db.agents.create_index("agent_id", unique=True)
    await db.agents.create_index("status")
    await db.agents.create_index("role")
    
    # trades collection
    await db.trades.create_index("trade_id", unique=True)
    await db.trades.create_index("buyer_id")
    await db.trades.create_index("seller_id")
    await db.trades.create_index("status")
    await db.trades.create_index("created_at")
    
    # ledger_entries collection (double-entry)
    await db.ledger_entries.create_index("entry_id", unique=True)
    await db.ledger_entries.create_index("trade_id")
    await db.ledger_entries.create_index("account")
    await db.ledger_entries.create_index("timestamp")
    
    # jobs collection
    await db.jobs.create_index("job_id", unique=True)
    await db.jobs.create_index("trade_id")
    await db.jobs.create_index("status")
    
    # payouts collection
    await db.payouts.create_index("payout_id", unique=True)
    await db.payouts.create_index("batch_id")
    await db.payouts.create_index("status")
    await db.payouts.create_index("paypal_payout_item_id")
    
    # orders/funding
    await db.funding_orders.create_index("order_id", unique=True)
    await db.funding_orders.create_index("agent_id")
    await db.funding_orders.create_index("status")
    
    # audit_log
    await db.audit_log.create_index("audit_id", unique=True)
    await db.audit_log.create_index("actor_id")
    await db.audit_log.create_index("action")
    await db.audit_log.create_index("timestamp")
    
    # idempotency_keys
    await db.idempotency_keys.create_index("key", unique=True)
    await db.idempotency_keys.create_index("expires_at", expireAfterSeconds=0)
    
    # approvals
    await db.approvals.create_index("approval_id", unique=True)
    await db.approvals.create_index("status")
    await db.approvals.create_index("created_at")
    
    print("Indexes created successfully")
