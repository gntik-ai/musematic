from __future__ import annotations

import logging as stdlib_logging
import sys
from collections.abc import Mapping
from contextvars import ContextVar, Token
from typing import Any

import jwt
import structlog
from starlette.requests import Request

_workspace_id: ContextVar[str | None] = ContextVar("workspace_id", default=None)
_goal_id: ContextVar[str | None] = ContextVar("goal_id", default=None)
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_span_id: ContextVar[str | None] = ContextVar("span_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_execution_id: ContextVar[str | None] = ContextVar("execution_id", default=None)

_CONTEXT_VARS: Mapping[str, ContextVar[str | None]] = {
    "workspace_id": _workspace_id,
    "goal_id": _goal_id,
    "correlation_id": _correlation_id,
    "trace_id": _trace_id,
    "span_id": _span_id,
    "user_id": _user_id,
    "execution_id": _execution_id,
}
_CONFIGURED: set[tuple[str, str]] = set()
_NOISY_STDLIB_LOGGERS = ("apscheduler",)

ContextTokens = dict[str, Token[str | None]]


def configure_logging(service_name: str, bounded_context: str) -> None:
    stdlib_logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=stdlib_logging.INFO,
        force=True,
    )
    for logger_name in _NOISY_STDLIB_LOGGERS:
        stdlib_logging.getLogger(logger_name).setLevel(stdlib_logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_service_metadata(service_name, bounded_context),
            _add_context_metadata,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
            structlog.processors.dict_tracebacks,
            _event_to_message,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    _CONFIGURED.add((service_name, bounded_context))


def get_logger(name: str | None = None) -> Any:
    if not _CONFIGURED:
        stdlib_logging.getLogger(__name__).warning(
            "Structured logging requested before configure_logging(); using default structlog "
            "configuration"
        )
    return structlog.get_logger(name)


def set_context_from_request(request: Request) -> ContextTokens:
    values: dict[str, str | None] = {
        "correlation_id": _first_non_empty(
            getattr(request.state, "correlation_id", None),
            request.headers.get("X-Correlation-ID"),
        ),
        "trace_id": _first_non_empty(
            request.headers.get("X-Trace-ID"),
            _trace_id_from_traceparent(request.headers.get("traceparent")),
        ),
        "workspace_id": _first_non_empty(
            getattr(request.state, "workspace_id", None),
            request.path_params.get("workspace_id"),
            request.headers.get("X-Workspace-ID"),
        ),
        "goal_id": _first_non_empty(
            getattr(request.state, "goal_id", None),
            request.path_params.get("goal_id"),
            request.headers.get("X-Goal-ID"),
            request.headers.get("X-Goal-Id"),
        ),
        "execution_id": _first_non_empty(
            request.path_params.get("execution_id"),
            request.headers.get("X-Execution-ID"),
        ),
        "user_id": None,
    }
    user = getattr(request.state, "user", None)
    if isinstance(user, Mapping):
        values["user_id"] = _first_non_empty(
            user.get("user_id"),
            user.get("principal_id"),
            user.get("sub"),
        )
    if values["user_id"] is None:
        values["user_id"] = _user_id_from_authorization(request.headers.get("Authorization"))
    return set_logging_context(**values)


def set_context_from_event_envelope(envelope: Any) -> ContextTokens:
    correlation = getattr(envelope, "correlation_context", None)
    trace_context = getattr(envelope, "trace_context", None)
    payload = getattr(envelope, "payload", None)
    return set_logging_context(
        workspace_id=_as_str(getattr(correlation, "workspace_id", None)),
        goal_id=_as_str(getattr(correlation, "goal_id", None)),
        correlation_id=_as_str(getattr(correlation, "correlation_id", None)),
        trace_id=_first_non_empty(
            _mapping_value(trace_context, "trace_id"),
            _mapping_value(payload, "trace_id"),
        ),
        span_id=_first_non_empty(
            _mapping_value(trace_context, "span_id"),
            _mapping_value(payload, "span_id"),
        ),
        user_id=_first_non_empty(
            _mapping_value(payload, "user_id"),
            _as_str(getattr(correlation, "user_id", None)),
        ),
        execution_id=_as_str(getattr(correlation, "execution_id", None)),
    )


def set_logging_context(**values: str | None) -> ContextTokens:
    tokens: ContextTokens = {}
    for key, value in values.items():
        context_var = _CONTEXT_VARS.get(key)
        if context_var is None:
            continue
        normalized = _as_str(value)
        if normalized is None:
            continue
        tokens[key] = context_var.set(normalized)
    return tokens


def clear_context(tokens: ContextTokens | None = None) -> None:
    if tokens is None:
        for context_var in _CONTEXT_VARS.values():
            context_var.set(None)
        return
    for key, token in reversed(tokens.items()):
        _CONTEXT_VARS[key].reset(token)


def _add_service_metadata(
    service_name: str,
    bounded_context: str,
) -> structlog.types.Processor:
    def processor(
        _logger: Any,
        _method_name: str,
        event_dict: structlog.types.EventDict,
    ) -> structlog.types.EventDict:
        event_dict.setdefault("service", service_name)
        event_dict.setdefault("bounded_context", bounded_context)
        return event_dict

    return processor


def _add_context_metadata(
    _logger: Any,
    _method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    for key, context_var in _CONTEXT_VARS.items():
        value = context_var.get()
        if value is not None:
            event_dict.setdefault(key, value)
    return event_dict


def _event_to_message(
    _logger: Any,
    _method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    if "message" not in event_dict and "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        normalized = _as_str(value)
        if normalized:
            return normalized
    return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _mapping_value(value: Any, key: str) -> str | None:
    if not isinstance(value, Mapping):
        return None
    return _as_str(value.get(key))


def _trace_id_from_traceparent(traceparent: str | None) -> str | None:
    if not traceparent:
        return None
    parts = traceparent.strip().split("-")
    if len(parts) < 2:
        return None
    return parts[1] or None


def _user_id_from_authorization(header: str | None) -> str | None:
    if not header or not header.startswith("Bearer "):
        return None
    token = header.removeprefix("Bearer ").strip()
    if not token:
        return None
    try:
        payload: Any = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return None
    if not isinstance(payload, Mapping):
        return None
    return _first_non_empty(payload.get("user_id"), payload.get("sub"))
