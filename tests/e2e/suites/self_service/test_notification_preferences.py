from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_preferences_matrix_roundtrip(self_service_client) -> None:
    current = await get_json(self_service_client, "/api/v1/me/notification-preferences")
    payload = {
        "per_channel_preferences": {
            **current.get("per_channel_preferences", {}),
            "security.session": ["in_app"],
        },
        "digest_mode": {**current.get("digest_mode", {}), "email": "daily"},
        "quiet_hours": {
            "start_time": "22:00",
            "end_time": "07:00",
            "timezone": "UTC",
        },
    }
    updated = await self_service_client.put(
        "/api/v1/me/notification-preferences",
        json=payload,
    )
    assert updated.status_code in {200, 202}, updated.text
    body = updated.json()
    assert body["per_channel_preferences"]["security.session"] == ["in_app"]


@pytest.mark.asyncio
async def test_mandatory_events_reject_all_channels_disabled(self_service_client) -> None:
    response = await self_service_client.put(
        "/api/v1/me/notification-preferences",
        json={"per_channel_preferences": {"security.session": []}},
    )
    assert response.status_code in {400, 422}


@pytest.mark.asyncio
async def test_quiet_hours_can_be_saved(self_service_client) -> None:
    response = await self_service_client.put(
        "/api/v1/me/notification-preferences",
        json={
            "quiet_hours": {
                "start_time": "23:00",
                "end_time": "06:00",
                "timezone": "Europe/Madrid",
            }
        },
    )
    assert response.status_code in {200, 202}, response.text
    assert response.json().get("quiet_hours", {}).get("timezone") == "Europe/Madrid"


@pytest.mark.asyncio
async def test_digest_mode_roundtrip(self_service_client) -> None:
    response = await self_service_client.put(
        "/api/v1/me/notification-preferences",
        json={"digest_mode": {"email": "hourly", "slack": "immediate"}},
    )
    assert response.status_code in {200, 202}, response.text
    digest_mode = response.json().get("digest_mode", {})
    assert digest_mode.get("email") == "hourly"


@pytest.mark.asyncio
async def test_test_notification_action(self_service_client) -> None:
    result = await post_json(
        self_service_client,
        "/api/v1/me/notification-preferences/test/security.session",
        {},
    )
    assert result.get("success") is True


@pytest.mark.asyncio
async def test_critical_preferences_keep_at_least_one_channel(self_service_client) -> None:
    preferences = await get_json(self_service_client, "/api/v1/me/notification-preferences")
    channels = preferences.get("per_channel_preferences", {}).get("incidents.resolved", ["in_app"])
    assert len(channels) >= 1
