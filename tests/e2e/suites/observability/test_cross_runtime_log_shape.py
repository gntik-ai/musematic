from __future__ import annotations

import pytest

from suites.observability._helpers import LEVELS, REQUIRED_FIELDS, log_lines, push_loki_log, query_loki_until, unique_event

pytestmark = [pytest.mark.e2e, pytest.mark.observability, pytest.mark.asyncio]


async def test_python_go_and_typescript_logs_share_field_shape(loki_client) -> None:
    event_id = unique_event("shape")
    common_fields = {
        "workspace_id": "workspace-shape",
        "goal_id": "goal-shape",
        "correlation_id": event_id,
        "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
        "span_id": "00f067aa0ba902b7",
        "user_id": "user-shape",
        "execution_id": "execution-shape",
    }
    runtimes = [
        ("api", "platform-control"),
        ("reasoning-engine", "platform-execution"),
        ("web", "frontend"),
    ]

    for service, bounded_context in runtimes:
        await push_loki_log(
            loki_client,
            service=service,
            bounded_context=bounded_context,
            level="warn",
            message=f"{event_id}.{service}",
            fields=common_fields,
        )

    payloads = []
    for service, bounded_context in runtimes:
        streams = await query_loki_until(
            loki_client,
            f'{{service="{service}",bounded_context="{bounded_context}",level="warn"}}',
            lambda result: any(event_id in line for stream in result for _ts, line in stream.get("values", [])),
        )
        payloads.extend(payload for _labels, payload in log_lines(streams) if payload.get("correlation_id") == event_id)

    assert len(payloads) >= len(runtimes)
    reference_keys = set(payloads[0])
    reference_types = {key: type(value) for key, value in payloads[0].items()}
    for payload in payloads:
        assert REQUIRED_FIELDS <= set(payload)
        assert payload["level"] in LEVELS
        assert set(payload) == reference_keys
        assert {key: type(value) for key, value in payload.items()} == reference_types
