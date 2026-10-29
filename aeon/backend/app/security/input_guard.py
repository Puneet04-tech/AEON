"""Reject hostile input early.

Rules:
  * no object keys starting with '$' or containing '.' (NoSQL operator injection)
  * bounded string length, no control characters
  * integer money within a sane range, never floats/bools/strings
  * identifiers are opaque ULIDs / slugs
"""
import re
from typing import Any

MAX_STRING = 2000
MAX_DEPTH = 8
ID_RE = re.compile(r"^[A-Za-z0-9_-]{3,64}$")


class InputRejected(ValueError):
    pass


def reject_unsafe_keys(value: Any, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise InputRejected("payload too deeply nested")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise InputRejected("non-string key")
            if key.startswith("$") or "." in key or key == "__proto__":
                raise InputRejected(f"illegal key: {key}")
            reject_unsafe_keys(item, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            reject_unsafe_keys(item, depth + 1)


def sanitize_string(value: str, max_len: int = MAX_STRING) -> str:
    if not isinstance(value, str):
        raise InputRejected("expected string")
    cleaned = "".join(ch for ch in value if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    cleaned = cleaned.strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len]
    return cleaned


def require_id(value: str, field: str = "id") -> str:
    if not isinstance(value, str) or not ID_RE.match(value):
        raise InputRejected(f"invalid {field}")
    return value


def require_money(value: Any, field: str = "amount_micro", minimum: int = 1,
                  maximum: int = 10**15) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputRejected(f"{field} must be an integer number of micro-USD")
    if value < minimum or value > maximum:
        raise InputRejected(f"{field} out of range")
    return value


def require_positive_int(value: Any, field: str, minimum: int = 1, maximum: int = 10**9) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputRejected(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise InputRejected(f"{field} out of range")
    return value
