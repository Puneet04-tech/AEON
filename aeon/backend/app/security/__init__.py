"""Security primitives: sessions/roles, HMAC signing, rate limiting, input guards."""
from .sessions import (  # noqa: F401
    Session,
    consume_scenario_quota,
    current_session,
    hash_password,
    issue_session,
    load_session,
    operator_login_configured,
    require_judge_or_operator,
    require_operator,
    require_role,
    require_viewer,
    revoke_session,
    verify_operator_password,
)
from .hmac_signing import sign, sign_bytes, verify  # noqa: F401
from .rate_limit import SlidingWindowLimiter, enforce  # noqa: F401
from .input_guard import (  # noqa: F401
    InputRejected,
    reject_unsafe_keys,
    require_id,
    require_money,
    require_positive_int,
    sanitize_string,
)
