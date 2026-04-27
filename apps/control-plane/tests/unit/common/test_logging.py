from __future__ import annotations

import asyncio
import json
import logging as stdlib_logging
from platform.common import logging as structured_logging
from platform.common.logging import (
    clear_context,
    configure_logging,
    get_logger,
    set_logging_context,
)
from platform.common.logging_constants import (
    HIGH_CARDINALITY_FORBIDDEN_LABELS,
    LOKI_LABEL_ALLOWLIST,
    REQUIRED_FIELDS,
)

import pytest
import structlog


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
