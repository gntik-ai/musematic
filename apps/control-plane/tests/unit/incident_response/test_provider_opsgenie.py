from __future__ import annotations

import json
from platform.incident_response.services.providers.base import ProviderError
from platform.incident_response.services.providers.opsgenie import OpsGenieClient

import httpx
import pytest

from tests.unit.incident_response.support import (
    RecordingSecretProvider,
    make_incident,
    make_integration,
)


@pytest.mark.asyncio
async def test_opsgenie_create_alert_matches_alert_api_v2_shape() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"requestId": "og-request"})

    client = OpsGenieClient(
        secret_provider=RecordingSecretProvider("genie-key"),
        timeout_seconds=1.0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    ref = await client.create_alert(
        integration=make_integration(provider="opsgenie"),
        incident=make_incident(),
        mapped_severity="P1",
    )

    assert ref.provider_reference == "og-request"
    assert requests[0].url == "https://api.opsgenie.com/v2/alerts"
    assert requests[0].headers["Authorization"] == "GenieKey genie-key"
    payload = json.loads(requests[0].content)
    assert payload["message"] == "Kafka lag above threshold"
    assert payload["alias"]
    assert payload["priority"] == "P1"
    assert payload["details"]["runbook_scenario"] == "kafka_lag"


@pytest.mark.asyncio
async def test_opsgenie_error_paths_mark_4xx_permanent_and_5xx_retryable() -> None:
    async def permanent(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(422)

    async def retryable(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(500)

    for handler, expected_retryable in [(permanent, False), (retryable, True)]:
        client = OpsGenieClient(
            secret_provider=RecordingSecretProvider("genie-key"),
            timeout_seconds=1.0,
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        with pytest.raises(ProviderError) as exc_info:
            await client.create_alert(
                integration=make_integration(provider="opsgenie"),
                incident=make_incident(),
                mapped_severity="P1",
            )
        assert exc_info.value.retryable is expected_retryable
