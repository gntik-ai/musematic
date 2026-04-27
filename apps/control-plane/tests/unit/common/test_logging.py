from __future__ import annotations

import asyncio
import json
import logging as stdlib_logging
from platform.common import logging as structured_logging
from platform.common.logging import (
    clear_context,
    configure_logging,
    get_logger,
    set_context_from_event_envelope,
    set_context_from_request,
    set_logging_context,
)
from platform.common.logging_constants import (
    HIGH_CARDINALITY_FORBIDDEN_LABELS,
    LOKI_LABEL_ALLOWLIST,
    REQUIRED_FIELDS,
)
from platform.common.middleware.kafka_logging_consumer_middleware import (
    run_with_event_logging_context,
    with_event_logging_context,
)
from types import SimpleNamespace

import jwt
import pytest
import structlog
from starlette.requests import Request


def _request(
    *,
    headers: dict[str, str] | None = None,
    path_params: dict[str, str] | None = None,
) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [
                (name.lower().encode("latin-1"), value.encode("latin-1"))
                for name, value in (headers or {}).items()
            ],
            "path_params": path_params or {},
        }
    )


def _read_json_line(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    captured = capsys.readouterr().out.strip().splitlines()
    assert captured
    return json.loads(captured[-1])


def test_configure_logging_outputs_required_json_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("api", "platform-control")

    structlog.get_logger("test").info("control-plane.ready")

    payload = _read_json_line(capsys)
    for field in REQUIRED_FIELDS:
        assert field in payload
    assert payload["service"] == "api"
    assert payload["bounded_context"] == "platform-control"
    assert payload["level"] == "info"
    assert payload["message"] == "control-plane.ready"


@pytest.mark.asyncio
async def test_contextvars_survive_await_boundary(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("worker", "platform-control")
    tokens = set_logging_context(
        workspace_id="workspace-1",
        goal_id="goal-1",
        correlation_id="corr-1",
        trace_id="trace-1",
        user_id="user-1",
        execution_id="exec-1",
    )
    try:
        await asyncio.sleep(0)
        structlog.get_logger("test").warning("background.processed")
    finally:
        clear_context(tokens)

    payload = _read_json_line(capsys)
    assert payload["workspace_id"] == "workspace-1"
    assert payload["goal_id"] == "goal-1"
    assert payload["correlation_id"] == "corr-1"
    assert payload["trace_id"] == "trace-1"
    assert payload["user_id"] == "user-1"
    assert payload["execution_id"] == "exec-1"


def test_high_cardinality_fields_stay_payload_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("api", "platform-control")
    tokens = set_logging_context(workspace_id="workspace-1", user_id="user-1")
    try:
        structlog.get_logger("test").error("request.failed")
    finally:
        clear_context(tokens)

    payload = _read_json_line(capsys)
    assert payload["workspace_id"] == "workspace-1"
    assert payload["user_id"] == "user-1"
    assert "labels" not in payload
    assert set(LOKI_LABEL_ALLOWLIST).isdisjoint(HIGH_CARDINALITY_FORBIDDEN_LABELS)


def test_get_logger_warns_if_structlog_not_configured(
    caplog: pytest.LogCaptureFixture,
) -> None:
    structured_logging._CONFIGURED.clear()
    stdlib_logging.getLogger("platform.common.logging").handlers.clear()

    with caplog.at_level(stdlib_logging.WARNING):
        logger = get_logger("unconfigured")

    logger.info("still.safe")
    assert "Structured logging requested before configure_logging()" in caplog.text


def test_get_logger_after_configuration_does_not_warn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_logging("api", "platform-control")

    with caplog.at_level(stdlib_logging.WARNING):
        logger = get_logger("configured")

    logger.info("configured.safe")
    assert "Structured logging requested before configure_logging()" not in caplog.text


def test_set_logging_context_ignores_unknown_and_blank_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("api", "platform-control")
    tokens = set_logging_context(unknown="ignored", workspace_id="   ")

    structlog.get_logger("test").info("context.blank")

    payload = _read_json_line(capsys)
    assert tokens == {}
    assert "workspace_id" not in payload


def test_event_to_message_preserves_existing_message() -> None:
    event = {"message": "kept", "event": "payload.event"}

    processed = structured_logging._event_to_message(None, "info", event)

    assert processed == {"message": "kept", "event": "payload.event"}


def test_set_context_from_request_prefers_state_and_user_mapping(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("api", "platform-control")
    request = _request(
        headers={
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "X-Workspace-ID": "workspace-header",
            "X-Execution-ID": "exec-1",
        },
        path_params={"workspace_id": "workspace-path", "goal_id": "goal-1"},
    )
    request.state.workspace_id = "workspace-state"
    request.state.correlation_id = "corr-state"
    request.state.user = {"principal_id": "user-state"}

    tokens = set_context_from_request(request)
    try:
        structlog.get_logger("test").info("request.context")
    finally:
        clear_context(tokens)

    payload = _read_json_line(capsys)
    assert payload["workspace_id"] == "workspace-state"
    assert payload["goal_id"] == "goal-1"
    assert payload["correlation_id"] == "corr-state"
    assert payload["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert payload["execution_id"] == "exec-1"
    assert payload["user_id"] == "user-state"


def test_set_context_from_request_uses_authorization_fallback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("api", "platform-control")
    token = jwt.encode({"sub": "user-token"}, "", algorithm="none")
    request = _request(headers={"Authorization": f"Bearer {token}", "X-Trace-ID": "trace-1"})

    tokens = set_context_from_request(request)
    try:
        structlog.get_logger("test").info("request.auth_context")
    finally:
        clear_context(tokens)

    payload = _read_json_line(capsys)
    assert payload["trace_id"] == "trace-1"
    assert payload["user_id"] == "user-token"


def test_set_context_from_request_ignores_invalid_authorization(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("api", "platform-control")
    request = _request(headers={"Authorization": "Bearer not-a-token"})

    tokens = set_context_from_request(request)
    try:
        structlog.get_logger("test").info("request.invalid_auth")
    finally:
        clear_context(tokens)

    payload = _read_json_line(capsys)
    assert "user_id" not in payload


def test_set_context_from_request_ignores_blank_authorization_and_bad_traceparent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("api", "platform-control")
    request = _request(headers={"Authorization": "Bearer   ", "traceparent": "malformed"})

    tokens = set_context_from_request(request)
    try:
        structlog.get_logger("test").info("request.blank_auth")
    finally:
        clear_context(tokens)

    payload = _read_json_line(capsys)
    assert "trace_id" not in payload
    assert "user_id" not in payload


def test_set_context_from_request_ignores_non_mapping_authorization_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("api", "platform-control")
    monkeypatch.setattr(structured_logging.jwt, "decode", lambda *args, **kwargs: "bad-payload")
    request = _request(headers={"Authorization": "Bearer token"})

    tokens = set_context_from_request(request)
    try:
        structlog.get_logger("test").info("request.non_mapping_auth")
    finally:
        clear_context(tokens)

    payload = _read_json_line(capsys)
    assert "user_id" not in payload


def test_set_context_from_event_envelope_reads_correlation_trace_and_payload(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("consumer", "platform-control")
    envelope = SimpleNamespace(
        correlation_context=SimpleNamespace(
            workspace_id="workspace-1",
            goal_id="goal-1",
            correlation_id="corr-1",
            user_id="user-correlation",
            execution_id="exec-1",
        ),
        trace_context={"trace_id": "trace-1", "span_id": "span-1"},
        payload={"trace_id": "payload-trace", "user_id": "user-payload"},
    )

    tokens = set_context_from_event_envelope(envelope)
    try:
        structlog.get_logger("test").info("event.context")
    finally:
        clear_context(tokens)

    payload = _read_json_line(capsys)
    assert payload["workspace_id"] == "workspace-1"
    assert payload["goal_id"] == "goal-1"
    assert payload["correlation_id"] == "corr-1"
    assert payload["trace_id"] == "trace-1"
    assert payload["span_id"] == "span-1"
    assert payload["user_id"] == "user-payload"
    assert payload["execution_id"] == "exec-1"


def test_set_context_from_event_envelope_ignores_non_mapping_payload(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("consumer", "platform-control")
    envelope = SimpleNamespace(
        correlation_context=SimpleNamespace(user_id="user-correlation"),
        trace_context=None,
        payload="not-a-mapping",
    )

    tokens = set_context_from_event_envelope(envelope)
    try:
        structlog.get_logger("test").info("event.non_mapping")
    finally:
        clear_context(tokens)

    payload = _read_json_line(capsys)
    assert payload["user_id"] == "user-correlation"
    assert "trace_id" not in payload


@pytest.mark.asyncio
async def test_run_with_event_logging_context_clears_context(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("consumer", "platform-control")
    envelope = SimpleNamespace(
        correlation_context=SimpleNamespace(
            workspace_id="workspace-1",
            correlation_id="corr-1",
            user_id="user-1",
        ),
        trace_context={"trace_id": "trace-1"},
        payload={},
    )
    handled: list[object] = []

    async def handler(current_envelope: object) -> None:
        handled.append(current_envelope)
        structlog.get_logger("test").info("event.handled")

    await run_with_event_logging_context(envelope, handler)
    structlog.get_logger("test").info("event.after")

    first_payload, second_payload = [
        json.loads(line) for line in capsys.readouterr().out.strip().splitlines()[-2:]
    ]
    assert handled == [envelope]
    assert first_payload["workspace_id"] == "workspace-1"
    assert first_payload["correlation_id"] == "corr-1"
    assert first_payload["trace_id"] == "trace-1"
    assert first_payload["user_id"] == "user-1"
    assert "workspace_id" not in second_payload


@pytest.mark.asyncio
async def test_with_event_logging_context_wraps_handler(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("consumer", "platform-control")
    envelope = SimpleNamespace(
        correlation_context=SimpleNamespace(workspace_id="workspace-2"),
        trace_context={},
        payload={},
    )

    async def handler(_current_envelope: object) -> None:
        structlog.get_logger("test").info("event.wrapped")

    await with_event_logging_context(handler)(envelope)

    payload = _read_json_line(capsys)
    assert payload["workspace_id"] == "workspace-2"


def test_clear_context_without_tokens_removes_all_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("api", "platform-control")
    set_logging_context(workspace_id="workspace-1", trace_id="trace-1")

    clear_context()
    structlog.get_logger("test").info("context.cleared")

    payload = _read_json_line(capsys)
    assert "workspace_id" not in payload
    assert "trace_id" not in payload
