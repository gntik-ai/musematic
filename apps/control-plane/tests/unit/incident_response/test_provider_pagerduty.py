from __future__ import annotations

import json
from platform.incident_response.services.providers.base import ProviderError, _redact_headers
from platform.incident_response.services.providers.pagerduty import PagerDutyClient

import httpx
import pytest

from tests.unit.incident_response.support import (
    RecordingSecretProvider,
    make_incident,
    make_integration,
)


@pytest.mark.asyncio
async def test_pagerduty_create_alert_matches_events_api_v2_shape() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"dedup_key": "pd-dedup"})

    client = PagerDutyClient(
        secret_provider=RecordingSecretProvider("routing-key"),
        timeout_seconds=1.0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    ref = await client.create_alert(
        integration=make_integration(provider="pagerduty"),
        incident=make_incident(),
        mapped_severity="critical",
    )

    assert ref.provider_reference == "pd-dedup"
    assert requests[0].url == "https://events.pagerduty.com/v2/enqueue"
    payload = json.loads(requests[0].content)
    assert payload["event_action"] == "trigger"
    assert payload["routing_key"] == "routing-key"
    assert payload["payload"]["severity"] == "critical"
    assert payload["payload"]["summary"] == "Kafka lag above threshold"
    assert payload["payload"]["custom_details"]["runbook_scenario"] == "kafka_lag"


@pytest.mark.asyncio
async def test_pagerduty_error_paths_mark_4xx_permanent_and_5xx_retryable() -> None:
    async def permanent(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(400, json={"error": "bad routing key"})

    async def retryable(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503, json={"error": "unavailable"})

    for handler, expected_retryable in [(permanent, False), (retryable, True)]:
        client = PagerDutyClient(
            secret_provider=RecordingSecretProvider("routing-key"),
            timeout_seconds=1.0,
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        with pytest.raises(ProviderError) as exc_info:
            await client.create_alert(
                integration=make_integration(provider="pagerduty"),
                incident=make_incident(),
                mapped_severity="critical",
            )
        assert exc_info.value.retryable is expected_retryable


@pytest.mark.asyncio
async def test_pagerduty_refuses_plain_text_endpoint() -> None:
    client = PagerDutyClient(
        secret_provider=RecordingSecretProvider("routing-key"),
        timeout_seconds=1.0,
        client=httpx.AsyncClient(),
    )
    client.base_url = "http://events.pagerduty.test/v2/enqueue"

    with pytest.raises(ProviderError) as exc_info:
        await client.create_alert(
            integration=make_integration(provider="pagerduty"),
            incident=make_incident(),
            mapped_severity="critical",
        )

    assert exc_info.value.retryable is False


def test_provider_log_header_redaction_masks_authorization_only() -> None:
    assert _redact_headers({"Authorization": "secret", "X-Trace": "trace"}) == {
        "Authorization": "<redacted>",
        "X-Trace": "trace",
    }
