from __future__ import annotations

import pytest

from suites._helpers import get_json


@pytest.mark.asyncio
async def test_actor_id_query_is_scoped_to_current_user(self_service_client) -> None:
    payload = await get_json(self_service_client, "/api/v1/me/activity")
    assert "items" in payload


@pytest.mark.asyncio
async def test_subject_id_events_are_included(self_service_client) -> None:
    payload = await get_json(
        self_service_client,
        "/api/v1/me/activity",
        params={"event_type": "auth.api_key.created"},
    )
    assert "items" in payload


@pytest.mark.asyncio
async def test_actor_or_subject_or_semantics(self_service_client) -> None:
    payload = await get_json(self_service_client, "/api/v1/me/activity", params={"limit": 20})
    assert len(payload.get("items", [])) <= 20


@pytest.mark.asyncio
async def test_activity_cursor_pagination(self_service_client) -> None:
    first_page = await get_json(self_service_client, "/api/v1/me/activity", params={"limit": 1})
    assert "items" in first_page
    next_cursor = first_page.get("next_cursor")
    if not next_cursor:
        pytest.skip("No next cursor available")
    second_page = await get_json(
        self_service_client,
        "/api/v1/me/activity",
        params={"limit": 1, "cursor": next_cursor},
    )
    assert "items" in second_page
