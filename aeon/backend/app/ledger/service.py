"""
AEON Ledger Service - Double-entry ledger with invariants, escrow, release, refund

This module implements the core double-entry ledger that records all transactions
between agents. Every state change writes an audit_log entry. Money is stored as
integer micro-USD (1 USD = 1,000,000).
"""
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.settings import settings
from app.security.hmac_signing import sign_payload, compute_hmac
from app.security.input_guard import validate_amount, validate_trade_data
import structlog

logger = structlog.get_logger()


class LedgerService:
    """Service for managing the double-entry ledger."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    async def record_posting(self, trade_id: str, from_account: str, 
                            to_account: str, amount_micros: int,
                            metadata: dict = None) -> dict:
        """Record a double-entry posting in the ledger.
        
        Creates two entries: a debit from one account and a credit to another.
        """
        entry_id = f"ledger_{trade_id}_{from_account}_{to_account}_{int(time.time())}"
        
        # Debit entry (from account)
        debit_entry = {
            "entry_id": entry_id + "_debit",
            "trade_id": trade_id,
            "account": from_account,
            "type": "debit",
            "amount_micros": -amount_micros,  # Negative for debit
            "timestamp": int(time.time()),
            "metadata": metadata or {},
        }
        
        # Credit entry (to account)
        credit_entry = {
            "entry_id": entry_id + "_credit",
            "trade_id": trade_id,
            "account": to_account,
            "type": "credit",
            "amount_micros": amount_micros,  # Positive for credit
            "timestamp": int(time.time()),
            "metadata": metadata or {},
        }
        
        # Write both entries
        await self.db.ledger_entries.insert_many([debit_entry, credit_entry])
        
        # Emit audit log
        await self.db.audit_log.insert_one({
            "audit_id": f"ledger_{entry_id}",
            "actor": "ledger_service",
            "action": "posting",
            "trade_id": trade_id,
            "details": {"from": from_account, "to": to_account, "amount_micros": amount_micros},
            "timestamp": int(time.time()),
        })
        
        logger.info("Ledger posting recorded", entry_id=entry_id, amount_micros=amount_micros)
        
        return {"debit": debit_entry, "credit": credit_entry}
    
    async def check_invariant(self) -> bool:
        """Check ledger invariant: total debits = total credits across all entries.
        
        This is a critical invariant that ensures the double-entry ledger is balanced.
        """
        pipeline = [
            {"$group": {
                "_id": None,
                "total_debit": {"$sum": {"$cond": [{"$lt": ["$amount_micros", 0]}, "$amount_micros", 0]}},
                "total_credit": {"$sum": {"$cond": [{"$gt": ["$amount_micros", 0]}, "$amount_micros", 0]}},
            }},
        ]
        
        result = await self.db.ledger_entries.aggregate(pipeline).to_list(length=1)
        
        if not result:
            return True  # No entries, invariant holds vacuously
        
        result = result[0]
        is_balanced = result["total_debit"] == result["total_credit"]
        
        if not is_balanced:
            logger.error("Ledger invariant failed", 
                        total_debit=result["total_debit"], 
                        total_credit=result["total_credit"])
        
        return is_balanced
    
    async def get_balances(self, account: str = None) -> dict:
        """Get account balances from the ledger.
        
        If account specified, returns balance for that account.
        If not, returns all account balances.
        """
        pipeline = [
            {"$group": {
                "_id": "$account",
                "balance_micros": {"$sum": "$amount_micros"},
            }},
        ]
        
        if account:
            pipeline.insert(0, {"$match": {"account": account}})
        
        result = await self.db.ledger_entries.aggregate(pipeline).to_list(length=None)
        
        balances = {}
        for entry in result:
            balances[entry["_id"]] = entry["balance_micros"]
        
        return balances
    
    async def get_invariant_summary(self) -> dict:
        """Get a summary of the ledger invariant status."""
        invariant_ok = await self.check_invariant()
        balances = await self.get_balances()
        
        total_debit = sum(abs(v) for v in balances.values() if v < 0)
        total_credit = sum(v for v in balances.values() if v > 0)
        
        return {
            "invariant_balanced": invariant_ok,
            "total_debit_micros": total_debit,
            "total_credit_micros": total_credit,
            "account_count": len(balances),
            "balances": balances,
        }