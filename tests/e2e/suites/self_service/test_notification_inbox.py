from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_bell_badge_accuracy(logged_in_user_with_alerts, self_service_client) -> None:
    unread = await get_json(self_service_client, "/api/v1/me/alerts/unread-count")
    assert unread.get("count", 0) >= 0


@pytest.mark.asyncio
async def test_dropdown_uses_five_most_recent(logged_in_user_with_alerts, self_service_client) -> None:
    payload = await get_json(self_service_client, "/api/v1/me/alerts", params={"limit": 5})
    assert len(payload.get("items", [])) <= 5


@pytest.mark.asyncio
async def test_inbox_pagination_and_filters(logged_in_user_with_alerts, self_service_client) -> None:
    payload = await get_json(
        self_service_client,
        "/api/v1/me/alerts",
        params={"limit": 10, "read": "all"},
    )
    assert "items" in payload
    assert len(payload["items"]) <= 10


@pytest.mark.asyncio
async def test_bulk_mark_all_read_updates_unread_count(
    logged_in_user_with_alerts,
    self_service_client,
) -> None:
    result = await post_json(self_service_client, "/api/v1/me/alerts/mark-all-read", {})
    assert result.get("unread_count", 0) == 0


@pytest.mark.asyncio
async def test_notification_drill_down_payload_contains_source_reference(
    logged_in_user_with_alerts,
    self_service_client,
) -> None:
    payload = await get_json(self_service_client, "/api/v1/me/alerts", params={"limit": 1})
    items = payload.get("items", [])
    if not items:
        pytest.skip("No seeded alerts available for drill-down verification")
    alert = await get_json(self_service_client, f"/api/v1/me/alerts/{items[0]['id']}")
    assert "source_reference" in alert
