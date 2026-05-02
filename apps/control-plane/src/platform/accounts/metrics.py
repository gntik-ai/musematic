"""Prometheus metric helpers for accounts features."""

from __future__ import annotations

from typing import Any


class _NoopMetric:
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

Counter: Any = _prometheus_client.Counter if _prometheus_client is not None else _NoopMetric
Histogram: Any = _prometheus_client.Histogram if _prometheus_client is not None else _NoopMetric

__all__ = ["Counter", "Histogram"]
