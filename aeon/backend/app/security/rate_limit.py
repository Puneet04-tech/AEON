"""Rate limiting middleware for AEON API"""
import time
from typing import Callable, Optional, Dict, Any
from slowapi import Limiter, rates
from slowapi.util import get_remote_address
from slowapi.errors import HTTPExceptionError

# Rate limiter - configured per settings
default_limiter = Limiter(
    default_limits=["100 per minute"],
    key_func=get_remote_address
)


def get_limiter() -> Limiter:
    """Get the default rate limiter instance."""
    return default_limiter


def check_rate_limit(
    request,
    limiter: Limiter = None,
    rate: str = None
) -> bool:
    """Check if request is within rate limits. Returns True if allowed."""
    if limiter is None:
        limiter = default_limiter
    
    try:
        if rate:
            # Use specific rate limit
            limiter = Limiter(
                default_limits=[rate],
                key_func=get_remote_address
            )
        return limiter.check(request)
    except Exception:
        # If rate limiting fails, allow the request
        return True