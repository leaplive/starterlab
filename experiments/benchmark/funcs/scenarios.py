"""Benchmark scenario functions — trivial work, different decorator overhead."""

from leap import adminonly, nolog, noregcheck, ratelimit


@nolog
@noregcheck
@ratelimit(False)
def noop_minimal() -> bool:
    """Absolute minimum overhead: no logging, no reg check, no rate limit."""
    return True


@nolog
@ratelimit(False)
def noop_regcheck() -> bool:
    """Registration check enabled. Measures DB lookup cost vs minimal."""
    return True


@noregcheck
@ratelimit(False)
def noop_logged() -> bool:
    """Logging enabled. Measures DuckDB INSERT cost vs minimal."""
    return True


@nolog
@noregcheck
def noop_rate_limited() -> bool:
    """Rate limited (default 120/min). Shows rate limiter overhead and 429 rejections."""
    return True


def noop_full() -> bool:
    """Full pipeline: registration check + rate limit + DuckDB logging."""
    return True


@adminonly
@nolog
@ratelimit(False)
def noop_adminonly() -> bool:
    """Admin-only access check. Measures session validation cost."""
    return True
