"""
AEON Guardrail Rules - Unit-validated rules for every state-changing operation

Guardrails are deterministic code that validates every LLM proposal before execution.
No LLM output is ever executed as code or used as a database query.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import structlog

logger = structlog.get_logger()


class GuardrailRuleResult:
    """Result of a guardrail rule evaluation."""
    
    def __init__(self, 
                 passed: bool,
                 reason: str = None,
                 violation_type: str = None,
                 suggested_action: str = None):
        self.passed = passed
        self.reason = reason
        self.violation_type = violation_type
        self.suggested_action = suggested_action
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "violation_type": self.violation_type,
            "suggested_action": self.suggested_action,
        }


# Price band guardrail - ensures price is within acceptable bounds
class PriceBandRule:
    """Ensures trade price is within acceptable bands."""
    
    def __init__(self, 
                 min_price_micros: int = 1000,  # 0.001 uUSD minimum
                 max_price_micros: int = 1000000000):  # 1000 uUSD maximum
        self.min_price = min_price_micros
        self.max_price = max_price_micros
    
    def evaluate(self, price_micros: int) -> GuardrailRuleResult:
        if price_micros < self.min_price:
            return GuardrailRuleResult(
                passed=False,
                reason=f"Price {price_micros} micros below minimum {self.min_price}",
                violation_type="price_too_low",
                suggested_action="increase_price"
            )
        if price_micros > self.max_price:
            return GuardrailRuleResult(
                passed=False,
                reason=f"Price {price_micros} micros exceeds maximum {self.max_price}",
                violation_type="price_too_high",
                suggested_action="reduce_quantity"
            )
        return GuardrailRuleResult(passed=True, reason="Price within acceptable band")


# Budget cap guardrail - ensures agent doesn't exceed budget
class BudgetCapRule:
    """Ensures agent stays within their budget/policy caps."""
    
    def __init__(self, 
                 budget_micros: int,
                 spent_so_far_micros: int = 0):
        self.budget = budget_micros
        self.spent = spent_so_far_micros
    
    def evaluate(self, additional_cost_micros: int) -> GuardrailRuleResult:
        total_after = self.spent + additional_cost_micros
        remaining = self.budget - total_after
        
        if total_after > self.budget:
            return GuardrailRuleResult(
                passed=False,
                reason=f"Would exceed budget: {total_after} > {self.budget}, remaining: {remaining}",
                violation_type="budget_exceeded",
                suggested_action="reduce_or_cancel"
            )
        
        if remaining < self.budget * 0.1:  # Warning at 10% remaining
            return GuardrailRuleResult(
                passed=True,
                reason=f"Budget nearly exhausted: {remaining} micros remaining ({remaining/self.budget*100:.1f}%)",
                violation_type="budget_warning",
                suggested_action="monitor_closely"
            )
        
        return GuardrailRuleResult(passed=True, reason=f"Within budget: {remaining} micros remaining")


# Allowlist guardrail - ensures counterparty is allowed
class AllowlistRule:
    """Ensures the counterparty is on the allowed list."""
    
    def __init__(self, allowed_counterparties: List[str] = None):
        self.allowed = set(allowed_counterparties or [])
    
    def evaluate(self, counterparty_id: str) -> GuardrailRuleResult:
        if self.allowed and counterparty_id not in self.allowed:
            return GuardrailRuleResult(
                passed=False,
                reason=f"Counterparty {counterparty_id} not on allowlist",
                violation_type="counterparty_not_allowed",
                suggested_action="check_allowlist"
            )
        return GuardrailRuleResult(passed=True, reason="Counterparty allowed")


# Velocity guardrail - prevents excessive trading frequency
class VelocityRule:
    """Ensures trading velocity is within acceptable limits."""
    
    def __init__(self, 
                 max_trades_per_hour: int = 50,
                 max_trades_per_day: int = 500):
        self.max_per_hour = max_trades_per_hour
        self.max_per_day = max_trades_per_day
        self._trade_counts: Dict[str, List[int]] = {}  # {period: [timestamps]}
    
    def record_trade(self, trade_timestamp: int, period: str = "hour"):
        """Record a trade for velocity tracking."""
        if period not in self._trade_counts:
            self._trade_counts[period] = []
        self._trade_counts[period].append(trade_timestamp)
        
        # Clean old entries
        now = trade_timestamp
        if period == "hour":
            cutoff = now - 3600
            self._trade_counts[period] = [t for t in self._trade_counts[period] if t > cutoff]
        elif period == "day":
            cutoff = now - 86400
            self._trade_counts[period] = [t for t in self._trade_counts[period] if t > cutoff]
    
    def evaluate(self, trade_timestamp: int, period: str = "hour") -> GuardrailRuleResult:
        self.record_trade(trade_timestamp, period)
        count = len(self._trade_counts.get(period, []))
        
        limit = self.max_per_hour if period == "hour" else self.max_per_day
        
        if count > limit:
            return GuardrailRuleResult(
                passed=False,
                reason=f"Velocity exceeded: {count} trades in {period} (limit: {limit})",
                violation_type="velocity_too_high",
                suggested_action="throttle_trading"
            )
        
        return GuardrailRuleResult(passed=True, reason=f"Velocity OK: {count}/{limit} trades in {period}")


# Approval threshold guardrail
class ApprovalThresholdRule:
    """Ensures transactions above threshold have operator approval."""
    
    def __init__(self, 
                 threshold_micros: int = 25000000,  # 25 uUSD
                 require_approval: bool = True):
        self.threshold = threshold_micros
        self.require_approval = require_approval
    
    def evaluate(self, amount_micros: int, has_approval: bool = False) -> GuardrailRuleResult:
        if amount_micros > self.threshold and not has_approval:
            return GuardrailRuleResult(
                passed=False,
                reason=f"Transaction {amount_micros} micros exceeds approval threshold {self.threshold} without approval",
                violation_type="approval_required",
                suggested_action="obtain_approval"
            )
        return GuardrailRuleResult(passed=True, reason="Approval status OK")