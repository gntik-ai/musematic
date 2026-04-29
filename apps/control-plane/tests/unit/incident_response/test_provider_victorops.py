from __future__ import annotations

import json
from platform.incident_response.services.providers.base import ProviderError
from platform.incident_response.services.providers.victorops import VictorOpsClient

import httpx
import pytest

from tests.unit.incident_response.support import (
    RecordingSecretProvider,
    make_incident,
    make_integration,
)


@pytest.mark.asyncio
async def test_victorops_create_alert_matches_rest_endpoint_shape() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"entity_id": "victorops-entity"})

    client = VictorOpsClient(
        secret_provider=RecordingSecretProvider("routing-key:routing-name"),
        timeout_seconds=1.0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    ref = await client.create_alert(
        integration=make_integration(provider="victorops"),
        incident=make_incident(),
        mapped_severity="CRITICAL",
    )

    assert ref.provider_reference == "victorops-entity"
    assert str(requests[0].url).endswith("/routing-key/routing-name")
    payload = json.loads(requests[0].content)
    assert payload["monitoring_tool"] == "musematic"
    assert payload["entity_id"]
    assert payload["state_message"] == "Consumer group lag has exceeded the on-call threshold."
    assert payload["state_start_time"] > 0
    assert payload["message_type"] == "CRITICAL"


@pytest.mark.asyncio
async def test_victorops_error_paths_mark_4xx_permanent_and_5xx_retryable() -> None:
    async def permanent(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(404)

    async def retryable(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(502)

    for handler, expected_retryable in [(permanent, False), (retryable, True)]:
        client = VictorOpsClient(
            secret_provider=RecordingSecretProvider("routing-key:routing-name"),
            timeout_seconds=1.0,
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        with pytest.raises(ProviderError) as exc_info:
            await client.create_alert(
                integration=make_integration(provider="victorops"),
                incident=make_incident(),
                mapped_severity="CRITICAL",
            )
        assert exc_info.value.retryable is expected_retryable
