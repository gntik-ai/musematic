from __future__ import annotations

import pytest

from suites.observability._helpers import OPTIONAL_FIELDS, REQUIRED_FIELDS, log_lines, push_loki_log, query_loki_until, unique_event

pytestmark = [pytest.mark.e2e, pytest.mark.observability, pytest.mark.asyncio]


RUNTIMES = [
    ("api", "platform-control"),
    ("worker", "platform-control"),
    ("scheduler", "platform-control"),
    ("runtime-controller", "platform-execution"),
    ("sandbox-manager", "platform-execution"),
    ("reasoning-engine", "platform-execution"),
    ("simulation-controller", "platform-simulation"),
    ("web", "frontend"),
    ("web-client", "frontend"),
]


async def test_structured_logs_queryable_with_required_labels_and_payload(loki_client) -> None:
    event_id = unique_event("log-ingestion")
    fields = {
        "workspace_id": "workspace-e2e",
        "goal_id": "goal-e2e",
        "correlation_id": event_id,
        "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
        "span_id": "00f067aa0ba902b7",
        "user_id": "user-e2e",
        "execution_id": "execution-e2e",
    }

    for service, bounded_context in RUNTIMES:
        await push_loki_log(
            loki_client,
            service=service,
            bounded_context=bounded_context,
            level="error",
            message=f"{event_id}.{service}",
            fields=fields,
        )

    for service, bounded_context in RUNTIMES:
        query = f'{{service="{service}",bounded_context="{bounded_context}",level="error"}}'
        streams = await query_loki_until(
            loki_client,
            query,
            lambda result: any(f"{event_id}.{service}" in line for stream in result for _ts, line in stream.get("values", [])),
        )
        matching = [
            (labels, payload)
            for labels, payload in log_lines(streams)
            if payload.get("message") == f"{event_id}.{service}"
        ]
        assert matching, (service, streams)
        labels, payload = matching[-1]
        assert labels["service"] == service
        assert labels["bounded_context"] == bounded_context
        assert labels["level"] == "error"
        assert REQUIRED_FIELDS <= set(payload)
        assert OPTIONAL_FIELDS <= set(payload)
        for high_cardinality in OPTIONAL_FIELDS - {"span_id"}:
            assert high_cardinality not in labels
