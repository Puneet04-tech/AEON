"""
AEON Guardrail Engine - Applies all guardrail rules to proposals and state changes

The engine is the deterministic gate between LLM proposals and execution.
Every state-changing endpoint must pass through this engine.
No LLM output is ever executed as code or used as a database query directly.
"""
from typing import Dict, Any, List, Optional, Tuple
from fastapi import Request
import structlog

from app.guardrails.rules import (
    PriceBandRule,
    BudgetCapRule,
    AllowlistRule,
    VelocityRule,
    ApprovalThresholdRule,
    GuardrailRuleResult,
)
from app.ledger.service import LedgerService
from app.security.hmac_signing import verify_payload

logger = structlog.get_logger()


class GuardrailEngine:
    """Central guardrail engine that validates all operations."""
    
    def __init__(self, 
                 ledger_service: LedgerService,
                 agent_budgets: Dict[str, int] = None,
                 allowed_counterparties: List[str] = None):
        self.ledger = ledger_service
        
        # Initialize rules
        self.price_rule = PriceBandRule()
        self.approval_rule = ApprovalThresholdRule()
        
        # Budget rules per agent
        self.agent_budgets = agent_budgets or {}
        self.budget_rules: Dict[str, BudgetCapRule] = {}
        for agent_id, budget in self.agent_budgets.items():
            self.budget_rules[agent_id] = BudgetCapRule(budget_micros=budget)
        
        # Allowlist
        self.allowlist = AllowlistRule(allowed_counterparties)
        
        # Velocity tracking
        self.velocity = VelocityRule()
    
    def evaluate_trade_proposal(self, 
                                buyer_id: str,
                                seller_id: str,
                                price_micros: int,
                                trade_timestamp: int,
                                agent_budgets: Dict[str, int] = None) -> Tuple[bool, List[GuardrailRuleResult]]:
        """Evaluate a trade proposal against all guardrail rules.
        
        Returns (all_passed, list_of_results)
        """
        results = []
        all_passed = True
        
        # 1. Price band check
        price_result = self.price_rule.evaluate(price_micros)
        results.append(("price_band", price_result))
        if not price_result.passed:
            all_passed = False
        
        # 2. Budget check per agent
        if agent_budgets and buyer_id in agent_budgets:
            budget_result = self.budget_rules.get(buyer_id, BudgetCapRule()).evaluate(price_micros)
            results.append(("budget", budget_result))
            if not budget_result.passed:
                all_passed = False
        
        # 3. Allowlist check
        allowlist_result = self.allowlist.evaluate(seller_id)
        results.append(("allowlist", allowlist_result))
        if not allowlist_result.passed:
            all_passed = False
        
        # 4. Velocity check
        velocity_result = self.velocity.evaluate(trade_timestamp, period="hour")
        results.append(("velocity", velocity_result))
        if not velocity_result.passed:
            all_passed = False
        
        # 5. Approval check for large transactions
        approval_result = self.approval_rule.evaluate(price_micros)
        results.append(("approval", approval_result))
        if not approval_result.passed:
            all_passed = False
        
        logger.info("Trade proposal guardrail evaluation", 
                    buyer_id=buyer_id, 
                    seller_id=seller_id,
                    price_micros=price_micros,
                    all_passed=all_passed,
                    results=[r[1].to_dict() for r in results])
        
        return all_passed, results
    
    def evaluate_funding_proposal(self,
                                  agent_id: str,
                                  amount_micros: int,
                                  has_approval: bool = False,
                                  agent_budget: int = None) -> Tuple[bool, List[GuardrailRuleResult]]:
        """Evaluate a funding proposal against guardrail rules."""
        results = []
        all_passed = True
        
        # 1. Amount validation
        if not (1 <= amount_micros <= 1000000000000):
            results.append(("amount_validation", GuardrailRuleResult(
                passed=False, reason="Amount out of valid range"
            )))
            all_passed = False
        else:
            results.append(("amount_validation", GuardrailRuleResult(passed=True, reason="Amount valid")))
        
        # 2. Budget check
        if agent_budget:
            budget_result = BudgetCapRule(agent_budget).evaluate(amount_micros)
            results.append(("budget", budget_result))
            if not budget_result.passed:
                all_passed = False
        
        # 3. Approval check for large amounts
        approval_result = self.approval_rule.evaluate(amount_micros, has_approval)
        results.append(("approval", approval_result))
        if not approval_result.passed:
            all_passed = False
        
        return all_passed, results
    
    def check_kill_switch_state(self, is_active: bool) -> GuardrailRuleResult:
        """Check kill switch state - if active, most operations should be blocked."""
        if is_active:
            return GuardrailRuleResult(
                passed=False,
                reason="System kill switch is active - all state changes blocked",
                violation_type="kill_switch_active",
                suggested_action="resolve_kill_switch_before_operation"
            )
        return GuardrailRuleResult(passed=True, reason="Kill switch inactive - operations allowed")