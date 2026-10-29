"""Input validation and sanitization guards for AEON API"""
import re
import json
from typing import Any, Dict, Optional, List


def validate_json(data: str, required_fields: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Validate JSON string and optionally check for required fields."""
    try:
        parsed = json.loads(data)
        if not isinstance(parsed, dict):
            return None
        if required_fields:
            for field in required_fields:
                if field not in parsed:
                    return None
        return parsed
    except (json.JSONDecodeError, ValueError):
        return None


def sanitize_string(
    value: str,
    max_length: int = 500,
    allow_unicode: bool = True
) -> str:
    """Sanitize a string value to prevent injection attacks."""
    if not isinstance(value, str):
        return ""
    
    # Strip control characters except newlines and tabs
    cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', value)
    
    # Limit length
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    
    return cleaned.strip()


def validate_agent_id(agent_id: str) -> bool:
    """Validate agent ID format."""
    if not agent_id or not isinstance(agent_id, str):
        return False
    # Agent IDs are alphanumeric with optional hyphens/underscores
    pattern = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')
    return bool(pattern.match(agent_id))


def validate_amount(amount: Any, min_val: int = 1, max_val: int = 1000000000000) -> bool:
    """Validate that an amount is a positive integer within bounds."""
    try:
        amt = int(amount)
        return min_val <= amt <= max_val
    except (ValueError, TypeError):
        return False


def validate_trade_data(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Validate trade creation data."""
    required = ["buyer_id", "seller_id", "price_micros", "job_id"]
    validated = validate_json(json.dumps(data), required_fields=required)
    if validated is None:
        return None
    
    # Validate specific fields
    if not validate_agent_id(validated.get("buyer_id", "")):
        return None
    if not validate_agent_id(validated.get("seller_id", "")):
        return None
    if not validate_amount(validated.get("price_micros"), min_val=1):
        return None
    
    return validated