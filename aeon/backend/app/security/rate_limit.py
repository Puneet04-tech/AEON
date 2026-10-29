"""In-process sliding-window rate limiting.

Single-process only (Render free tier runs one instance). Per-key windows are
kept in memory; the blueprint calls for rate limits, not distributed ones.
"""
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

from fastapi import HTTPException, Request, status


class SlidingWindowLimiter:
    def __init__(self, window_seconds: int = 60, max_requests: int = 120):
        self.window = window_seconds
        self.max_requests = max_requests
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> Tuple[bool, int, float]:
        now = time.monotonic()
        bucket = self._hits[key]
        cutoff = now - self.window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        allowed = len(bucket) < self.max_requests
        if allowed:
            bucket.append(now)
        remaining = max(0, self.max_requests - len(bucket))
        reset = (bucket[0] + self.window) if bucket else now + self.window
        return allowed, remaining, reset

    def reset(self) -> None:
        self._hits.clear()


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def enforce(limiter: SlidingWindowLimiter, request: Request, scope: str = "") -> None:
    key = f"{scope}:{client_key(request)}"
    allowed, remaining, reset = limiter.hit(key)
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Rate limit exceeded",
            headers={"Retry-After": str(max(1, int(reset - time.monotonic())))},
        )
