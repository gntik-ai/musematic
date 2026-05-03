"""Prometheus metrics for the abuse-prevention bounded context (UPD-050).

Mirrors the fail-soft pattern in ``platform/marketplace/metrics.py``.
"""

from __future__ import annotations

from typing import Any


class _NoopMetric:  # pragma: no cover - used only when prometheus_client is unavailable
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def labels(self, *_args: Any, **_kwargs: Any) -> _NoopMetric:
        return self

    def inc(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def observe(self, *_args: Any, **_kwargs: Any) -> None:
        return None


_prometheus_client: Any
try:  # pragma: no cover
    import prometheus_client as _prometheus_client
except Exception:  # pragma: no cover
    _prometheus_client = None

Counter: Any = (
    _prometheus_client.Counter if _prometheus_client is not None else _NoopMetric
)
Histogram: Any = (
    _prometheus_client.Histogram if _prometheus_client is not None else _NoopMetric
)


abuse_velocity_hits_total = Counter(
    "abuse_velocity_hits_total",
    "Signup-velocity threshold hits, by counter dimension.",
    ["counter"],  # 'ip' | 'asn' | 'email_domain'
)

abuse_disposable_email_blocks_total = Counter(
    "abuse_disposable_email_blocks_total",
    "Signup attempts refused because the email domain is on the disposable list.",
)

abuse_captcha_failures_total = Counter(
    "abuse_captcha_failures_total",
    "CAPTCHA verification failures, by reason.",
    ["reason"],  # 'token_missing' | 'token_invalid' | 'token_replayed' | 'provider_error'
)

abuse_geo_blocks_total = Counter(
    "abuse_geo_blocks_total",
    "Signup attempts refused by geo-policy, by country code.",
    ["country"],
)

abuse_fraud_score_high_total = Counter(
    "abuse_fraud_score_high_total",
    "Fraud-scoring callbacks above the configured threshold.",
)

abuse_suspension_created_total = Counter(
    "abuse_suspension_created_total",
    "Account suspensions created, by reason.",
    ["reason"],
)

abuse_suspension_lifted_total = Counter(
    "abuse_suspension_lifted_total",
    "Account suspensions lifted by a super admin.",
)

abuse_velocity_redis_errors_total = Counter(
    "abuse_velocity_redis_errors_total",
    "Velocity-counter Redis operations that failed; signup is refused (fail-closed).",
)

abuse_signup_guard_duration_seconds = Histogram(
    "abuse_signup_guard_duration_seconds",
    "Time spent in each signup-guard branch.",
    ["guard"],  # 'velocity' | 'disposable' | 'captcha' | 'geo_block' | 'fraud_scoring'
)


__all__ = [
    "abuse_captcha_failures_total",
    "abuse_disposable_email_blocks_total",
    "abuse_fraud_score_high_total",
    "abuse_geo_blocks_total",
    "abuse_signup_guard_duration_seconds",
    "abuse_suspension_created_total",
    "abuse_suspension_lifted_total",
    "abuse_velocity_hits_total",
    "abuse_velocity_redis_errors_total",
]
