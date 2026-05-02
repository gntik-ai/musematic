"""Prometheus metric helpers for accounts features."""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - prometheus_client is installed in runtime images
    from prometheus_client import Counter, Histogram
except Exception:  # pragma: no cover

    class _NoopMetric:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def labels(self, *_args: Any, **_kwargs: Any) -> _NoopMetric:
            return self

        def inc(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def observe(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    Counter = _NoopMetric
    Histogram = _NoopMetric

__all__ = ["Counter", "Histogram"]
