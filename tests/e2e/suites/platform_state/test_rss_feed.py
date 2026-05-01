from __future__ import annotations

import pytest

from suites.ui_playwright import route_status_app_apis

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_rss_feed_is_valid_and_reflects_incident_lifecycle(
    ui_page,
    platform_status_url: str,
) -> None:
    feedparser = pytest.importorskip("feedparser")
    await route_status_app_apis(ui_page)

    response = await ui_page.goto(
        f"{platform_status_url.rstrip('/')}/api/v1/public/status/feed.rss",
    )
    assert response is not None
    parsed = feedparser.parse(await response.text())

    assert parsed.bozo is False
    assert parsed.feed.title == "Musematic Platform Status"
    assert any(entry.title == "Elevated API latency" for entry in parsed.entries)
