"""
AEON Ledger Invariants - Critical correctness checks for the double-entry ledger

These invariants ensure the ledger remains correct and auditable under all conditions,
including concurrent writes, idempotent operations, and failure recovery.
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta


class LedgerInvariants:
    """Collection of ledger invariants that must always hold."""
    
    @staticmethod
    def verify_double_entry(entry_set: List[dict]) -> bool:
        """Verify that a set of ledger entries forms a valid double-entry.
        
        For every debit, there must be a corresponding credit of equal amount.
        """
        total_debits = sum(e["amount_micros"] for e in entry_set if e["type"] == "debit")
        total_credits = sum(e["amount_micros"] for e in entry_set if e["type"] == "credit")
        
        # Debits should be negative, credits positive
        # The sum should be zero for a valid double-entry
        return total_debits + total_credits == 0
    
    @staticmethod
    def verify_no_negative_balances(balances: Dict[str, int]) -> bool:
        """Verify that no account has a negative balance (overdraft)."""
        for account, balance in balances.items():
            if balance < 0:
                return False
        return True
    
    @staticmethod
    def verify_idempotency_key_not_expired(expires_at: int) -> bool:
        """Verify that an idempotency key hasn't expired.
        
        expires_at is a Unix timestamp.
        """
        now = int(datetime.utcnow().timestamp())
        return now <= expires_at
    
    @staticmethod
    def verify_audit_completeness(audit_entries: List[dict], 
                                  expected_actions: List[str]) -> bool:
        """Verify that all expected actions are recorded in the audit log."""
        recorded_actions = {e["action"] for e in audit_entries}
        return all(action in recorded_actions for action in expected_actions)
    
    @staticmethod
    def verify_timestamp_ordering(audit_entries: List[dict]) -> bool:
        """Verify that audit log entries are in chronological order."""
        timestamps = [e["timestamp"] for e in audit_entries]
        return all(timestamps[i] <= timestamps[i+1] for i in range(len(timestamps)-1))