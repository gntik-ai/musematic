from __future__ import annotations

from typing import Any

import pytest

from journeys.conftest import AuthenticatedAsyncClient, JourneyContext
from journeys.helpers.narrative import journey_step
from suites._helpers import assert_eventually
from suites.ui_playwright import route_platform_shell_apis, ui_page as ui_page  # noqa: F401

# Cross-context inventory:
# - auth
# - audit
# - interactions
# - notifications
# - workspaces

JOURNEY_ID = "j21"
TIMEOUT_SECONDS = 240


async def _json(client: AuthenticatedAsyncClient, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    response = await client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json() if response.content else {}


def assert_status_snapshot_shape(snapshot: dict[str, Any]) -> None:
    assert "overall_state" in snapshot
    assert isinstance(snapshot.get("active_incidents"), list)
    assert isinstance(snapshot.get("components"), list)


def assert_incident_present(snapshot: dict[str, Any], incident_id: str) -> None:
    assert snapshot["overall_state"] in {"degraded", "partial_outage", "full_outage"}
    assert any(
        item.get("id") == incident_id
        or "J21 synthetic control-plane latency" in str(item.get("title"))
        for item in snapshot.get("active_incidents", [])
    )


def assert_feed_mentions_incident(response: Any) -> None:
    assert response.status_code == 200
    assert "J21 synthetic control-plane latency" in response.text


@pytest.mark.journey
@pytest.mark.j21_platform_state
@pytest.mark.timeout(TIMEOUT_SECONDS)
@pytest.mark.asyncio
async def test_j21_platform_state_visibility_loop(
    operator_client: AuthenticatedAsyncClient,
    journey_context: JourneyContext,
    db,
    ui_page,
    platform_ui_url: str,
) -> None:
    email = f"{journey_context.prefix}status-subscriber@e2e.test"
    incident_id: str | None = None

    with journey_step("Public status baseline exposes component inventory"):
        baseline = await _json(operator_client, "GET", "/api/v1/public/status")
        assert_status_snapshot_shape(baseline)

    with journey_step("Visitor submits an email update subscription"):
        await _json(
            operator_client,
            "POST",
            "/api/v1/public/subscribe/email",
            json={"email": email, "scope_components": ["control-plane-api"]},
        )

    with journey_step("Visitor receives the confirmation token"):
        token_payload = await assert_eventually(
            lambda: _json(
                operator_client,
                "GET",
                "/api/v1/_e2e/status-subscriptions/tokens",
                params={"email": email},
            ),
            lambda payload: bool(payload.get("confirmation_token")),
            timeout=20,
            message="status subscription confirmation token was not captured",
        )

    with journey_step("Visitor confirms the email subscription"):
        await _json(
            operator_client,
            "GET",
            "/api/v1/public/subscribe/email/confirm",
            params={"token": token_payload["confirmation_token"]},
        )

    with journey_step("Operator triggers a synthetic status-page incident"):
        incident = await _json(
            operator_client,
            "POST",
            "/api/v1/_e2e/incidents/trigger",
            json={
                "scenario": "status-page",
                "severity": "warning",
                "title": "J21 synthetic control-plane latency",
                "description": "Synthetic incident for platform-state journey.",
            },
        )
        incident_id = str(incident["incident_id"])

    with journey_step("Public status endpoint reflects the incident within sixty seconds"):
        snapshot = await assert_eventually(
            lambda: _json(operator_client, "GET", "/api/v1/public/status"),
            lambda payload: any(
                item.get("id") == incident_id
                or "J21 synthetic control-plane latency" in str(item.get("title"))
                for item in payload.get("active_incidents", [])
            ),
            timeout=60,
            message="public status did not show the synthetic incident",
        )
        assert_incident_present(snapshot, incident_id)

    with journey_step("Authenticated shell banner displays the active incident"):
        await route_platform_shell_apis(ui_page, maintenance_state="incident")
        await ui_page.goto(f"{platform_ui_url.rstrip('/')}/home/")
        playwright_api = pytest.importorskip("playwright.async_api")
        await playwright_api.expect(ui_page.get_by_text("Active incident").first).to_be_visible()

    with journey_step("Subscriber email delivery is represented in the dispatch ledger"):
        await assert_eventually(
            lambda: db.fetchval(
                """
                SELECT count(*)
                  FROM subscription_dispatches dispatch
                  JOIN status_subscriptions subscription
                    ON subscription.id = dispatch.subscription_id
                 WHERE subscription.target = $1
                   AND dispatch.event_kind = 'incident.created'
                   AND dispatch.outcome = 'sent'
                """,
                email,
            ),
            lambda count: int(count or 0) >= 1,
            timeout=120,
            message="status subscriber dispatch was not delivered",
        )

    with journey_step("RSS feed includes the same incident"):
        feed = await operator_client.get("/api/v1/public/status/feed.rss")
        feed.raise_for_status()
        assert_feed_mentions_incident(feed)

    with journey_step("Resolving the incident clears public status surfaces"):
        assert incident_id is not None
        await _json(
            operator_client,
            "POST",
            "/api/v1/_e2e/incidents/resolve",
            json={"incident_id": incident_id},
        )
        await assert_eventually(
            lambda: _json(operator_client, "GET", "/api/v1/public/status"),
            lambda payload: all(
                item.get("id") != incident_id for item in payload.get("active_incidents", [])
            ),
            timeout=10,
            message="public status did not clear the resolved incident",
        )
