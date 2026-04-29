from __future__ import annotations

import pytest

from .servers import provider_mock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "path", "payload", "reference_field"),
    [
        (
            "pagerduty",
            "/v2/enqueue",
            {
                "event_action": "trigger",
                "routing_key": "mock-routing-key",
                "dedup_key": "incident-1",
                "payload": {"summary": "Kafka lag", "severity": "critical"},
            },
            "dedup_key",
        ),
        (
            "opsgenie",
            "/v2/alerts",
            {
                "message": "Kafka lag",
                "alias": "incident-1",
                "priority": "P1",
            },
            "requestId",
        ),
        (
            "victorops",
            "/integrations/generic/20131114/alert/key/route",
            {
                "monitoring_tool": "musematic",
                "entity_id": "incident-1",
                "message_type": "CRITICAL",
            },
            "entity_id",
        ),
    ],
)
async def test_provider_mocks_return_success_shapes(
    provider: str,
    path: str,
    payload: dict[str, object],
    reference_field: str,
) -> None:
    mock = provider_mock(provider)  # type: ignore[arg-type]
    async with mock.client() as client:
        response = await client.post(path, json=payload)

    assert response.status_code == 202
    assert response.json()[reference_field] == "incident-1"
    assert mock.requests[0]["json"] == payload


@pytest.mark.asyncio
async def test_provider_mocks_return_retryable_error_shape() -> None:
    mock = provider_mock("pagerduty", status_code=503)
    async with mock.client() as client:
        response = await client.post(
            "/v2/enqueue",
            json={
                "event_action": "trigger",
                "routing_key": "mock-routing-key",
                "dedup_key": "incident-1",
            },
        )

    assert response.status_code == 503
    assert response.json() == {
        "provider": "pagerduty",
        "status": "error",
        "message": "mock pagerduty returned HTTP 503",
        "retryable": True,
    }
