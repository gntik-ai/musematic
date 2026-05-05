"""Tenant-BC Prometheus metrics.

UPD-053 (106) US4 — DNS automation observability:
    - tenants_dns_automation_duration_seconds (Histogram, label=action)
    - tenants_dns_automation_failed_total (Counter, labels=action,slug)

Both metrics are emitted from ``HetznerDnsAutomationClient`` /
``MockDnsAutomationClient`` so the dashboard panels in
``deploy/helm/observability/templates/dashboards/tenants.yaml`` and the
``WildcardCertRenewalFailing`` alert in
``deploy/helm/observability/templates/alerts/cert-manager-wildcard.yaml``
can render. The module gracefully degrades to no-op metrics when
``prometheus_client`` is not importable (e.g. in unit tests that don't
spin up a registry).
"""
from __future__ import annotations

from typing import Any


class _NoopMetric:  # pragma: no cover — only when prometheus_client is missing
    def __init__(self, *_a: Any, **_kw: Any) -> None:
        pass

    def labels(self, *_a: Any, **_kw: Any) -> _NoopMetric:
        return self

    def inc(self, *_a: Any, **_kw: Any) -> None:
        return None

    def observe(self, *_a: Any, **_kw: Any) -> None:
        return None


_prometheus_client: Any
try:  # pragma: no cover — prometheus_client is in the runtime image
    import prometheus_client as _prometheus_client
except Exception:  # pragma: no cover
    _prometheus_client = None


_Counter: Any = (
    _prometheus_client.Counter if _prometheus_client is not None else _NoopMetric
)
_Histogram: Any = (
    _prometheus_client.Histogram if _prometheus_client is not None else _NoopMetric
)


# Singletons — Prometheus refuses duplicate registration on the global
# REGISTRY, so guard with try/except to keep ``import platform.tenants.metrics``
# idempotent when modules reload (autoreload, pytest collection, etc.).
def _safe_register(factory: Any, name: str, doc: str, labels: list[str]) -> Any:
    try:
        return factory(name, doc, labels)
    except Exception:  # pragma: no cover — duplicated registration in tests
        if _prometheus_client is None:
            return _NoopMetric()
        existing = _prometheus_client.REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
        return existing if existing is not None else _NoopMetric()


tenants_dns_automation_duration_seconds = _safe_register(
    _Histogram,
    "tenants_dns_automation_duration_seconds",
    "Wall-clock seconds for one DNS-automation lifecycle action (create or remove).",
    ["action"],
)

tenants_dns_automation_failed_total = _safe_register(
    _Counter,
    "tenants_dns_automation_failed_total",
    "Number of DNS-automation lifecycle actions that exhausted the retry budget.",
    ["action", "slug"],
)


__all__ = [
    "tenants_dns_automation_duration_seconds",
    "tenants_dns_automation_failed_total",
]
