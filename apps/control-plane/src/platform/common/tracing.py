from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import nullcontext
from functools import wraps
from typing import Any, ParamSpec, TypeVar

try:
    from opentelemetry import trace as _trace
except ImportError:  # pragma: no cover - fallback for minimal test environments
    class _TraceShim:
        @staticmethod
        def get_tracer(_name: str) -> _TraceShim:
            return _TraceShim()

        def start_as_current_span(self, _span_name: str) -> nullcontext[None]:
            return nullcontext()

    _trace_impl: Any = _TraceShim()
else:
    _trace_impl = _trace

trace: Any = _trace_impl

P = ParamSpec("P")
R = TypeVar("R")


def traced_async(
    span_name: str,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            tracer = trace.get_tracer(func.__module__)
            with tracer.start_as_current_span(span_name):
                return await func(*args, **kwargs)

        return wrapper

    return decorator
