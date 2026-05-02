"""Prometheus metrics for the UPD-049 marketplace surfaces.

Mirrors the helper pattern in ``platform/accounts/metrics.py`` so a
missing ``prometheus_client`` install (e.g. test environment) degrades
to no-ops rather than ImportError.

The four counters and one histogram below give the operations dashboard
(see ``deploy/helm/platform/templates/grafana-dashboards/marketplace.yaml``)
its data:

- ``marketplace_submissions_total{category}`` — public-marketplace submissions
- ``marketplace_review_decisions_total{decision}`` — approve/reject counts
- ``marketplace_forks_total{target_scope}`` — fork operations by scope
- ``marketplace_rate_limit_refusals_total`` — 429 refusals from the
  per-submitter sliding-window cap (FR-009)
- ``marketplace_review_age_seconds`` — histogram of submission-to-decision
  durations (operational SLA per SC-007)
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
try:  # pragma: no cover - prometheus_client is installed in runtime images
    import prometheus_client as _prometheus_client
except Exception:  # pragma: no cover
    _prometheus_client = None

Counter: Any = (
    _prometheus_client.Counter if _prometheus_client is not None else _NoopMetric
)
Histogram: Any = (
    _prometheus_client.Histogram if _prometheus_client is not None else _NoopMetric
)


marketplace_submissions_total = Counter(
    "marketplace_submissions_total",
    "Public-marketplace submissions transitioned to pending_review.",
    ["category"],
)

marketplace_review_decisions_total = Counter(
    "marketplace_review_decisions_total",
    "Marketplace review decisions made by platform staff.",
    ["decision"],  # 'approved' | 'rejected'
)

marketplace_forks_total = Counter(
    "marketplace_forks_total",
    "Fork operations against marketplace agents.",
    ["target_scope"],  # 'workspace' | 'tenant'
)

marketplace_rate_limit_refusals_total = Counter(
    "marketplace_rate_limit_refusals_total",
    "Public-marketplace submissions refused by the per-submitter rate limiter.",
)

marketplace_review_age_seconds = Histogram(
    "marketplace_review_age_seconds",
    "Time from public-marketplace submission to a review decision.",
    ["decision"],
    buckets=(60, 300, 1800, 7200, 28800, 86400, 259200, 604800, 1209600),
)


__all__ = [
    "marketplace_forks_total",
    "marketplace_rate_limit_refusals_total",
    "marketplace_review_age_seconds",
    "marketplace_review_decisions_total",
    "marketplace_submissions_total",
]
