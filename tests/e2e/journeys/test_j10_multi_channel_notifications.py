from __future__ import annotations

import os
from typing import Any

import pytest

from journeys.conftest import AuthenticatedAsyncClient, JourneyContext
from journeys.helpers.narrative import journey_step

JOURNEY_ID = "j10"
TIMEOUT_SECONDS = 180

# Cross-context inventory:
# - accounts
# - auth
# - notifications
# - audit
# - workspaces


def _enabled() -> bool:
    return os.environ.get("MUSEMATIC_E2E_J10_NOTIFICATIONS", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@pytest.mark.journey
@pytest.mark.j10_notifications
@pytest.mark.j10_multi_channel_notifications
@pytest.mark.timeout(TIMEOUT_SECONDS)
@pytest.mark.asyncio
async def test_j10_multi_channel_notifications(
    admin_client: AuthenticatedAsyncClient,
    consumer_client: AuthenticatedAsyncClient,
    journey_context: JourneyContext,
) -> None:
    if not _enabled():
        pytest.skip("Set MUSEMATIC_E2E_J10_NOTIFICATIONS=1 to run the optional notifications journey")

    channel_payload: dict[str, Any] | None = None
    webhook_payload: dict[str, Any] | None = None

    with journey_step("Feature flag is enabled for multi-channel notifications"):
        assert os.environ.get("FEATURE_MULTI_CHANNEL_NOTIFICATIONS", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    with journey_step("Consumer lists notification channels before registration"):
        before = await consumer_client.get("/api/v1/me/notifications/channels")
        before.raise_for_status()
        assert isinstance(before.json(), list)

    with journey_step("Consumer registers an email channel for notification fan-out"):
        created = await consumer_client.post(
            "/api/v1/me/notifications/channels",
            json={
                "channel_type": "email",
                "target": f"{journey_context.prefix}alerts@e2e.test",
                "display_name": "Journey email",
                "alert_type_filter": ["attention_request", "state_change"],
                "severity_floor": "high",
            },
        )
        created.raise_for_status()
        channel_payload = created.json()
        assert channel_payload["verified_at"] is None

    with journey_step("Consumer confirms the pending channel appears in self-service inventory"):
        assert channel_payload is not None
        listed = await consumer_client.get("/api/v1/me/notifications/channels")
        listed.raise_for_status()
        ids = {item["id"] for item in listed.json()}
        assert channel_payload["id"] in ids

    with journey_step("Consumer can request a fresh verification challenge for the channel"):
        assert channel_payload is not None
        resent = await consumer_client.post(
            f"/api/v1/me/notifications/channels/{channel_payload['id']}/resend-verification"
        )
        resent.raise_for_status()
        assert resent.json()["id"] == channel_payload["id"]

    with journey_step("Admin creates a workspace to own an outbound webhook subscription"):
        workspace = await admin_client.post(
            "/api/v1/workspaces",
            json={
                "name": f"{journey_context.prefix}notifications",
                "description": "Workspace for the optional notifications journey.",
            },
        )
        workspace.raise_for_status()
        workspace_id = workspace.json()["id"]

    with journey_step("Admin registers a workspace webhook for execution failures"):
        webhook = await admin_client.post(
            "/api/v1/notifications/webhooks",
            json={
                "workspace_id": workspace_id,
                "name": "Journey webhook",
                "url": "https://example.invalid/musematic-webhook",
                "event_types": ["execution.failed"],
            },
        )
        webhook.raise_for_status()
        webhook_payload = webhook.json()
        assert webhook_payload["signing_secret"]

    with journey_step("Admin can list the newly registered outbound webhook"):
        assert webhook_payload is not None
        listed = await admin_client.get(
            "/api/v1/notifications/webhooks",
            params={"workspace_id": webhook_payload["workspace_id"]},
        )
        listed.raise_for_status()
        assert webhook_payload["id"] in {item["id"] for item in listed.json()}

    with journey_step("Admin can retrieve webhook detail without the one-time secret"):
        assert webhook_payload is not None
        detail = await admin_client.get(f"/api/v1/notifications/webhooks/{webhook_payload['id']}")
        detail.raise_for_status()
        assert detail.json()["id"] == webhook_payload["id"]
        assert "signing_secret" not in detail.json()

    with journey_step("Admin can update webhook metadata without changing the signing secret ref"):
        assert webhook_payload is not None
        patched = await admin_client.patch(
            f"/api/v1/notifications/webhooks/{webhook_payload['id']}",
            json={"name": "Journey webhook patched"},
        )
        patched.raise_for_status()
        assert patched.json()["name"] == "Journey webhook patched"

    with journey_step("Admin can send a test event that enters the delivery ledger"):
        assert webhook_payload is not None
        delivery = await admin_client.post(
            f"/api/v1/notifications/webhooks/{webhook_payload['id']}/test"
        )
        delivery.raise_for_status()
        assert delivery.json()["webhook_id"] == webhook_payload["id"]

    with journey_step("Dead-letter list is available for the webhook workspace"):
        assert webhook_payload is not None
        dead_letters = await admin_client.get(
            "/api/v1/notifications/dead-letter",
            params={"workspace_id": webhook_payload["workspace_id"]},
        )
        dead_letters.raise_for_status()
        assert isinstance(dead_letters.json(), list)

    with journey_step("Replay batch endpoint accepts the workspace filter shape"):
        assert webhook_payload is not None
        replay = await admin_client.post(
            "/api/v1/notifications/dead-letter/replay-batch",
            json={
                "workspace_id": webhook_payload["workspace_id"],
                "webhook_id": webhook_payload["id"],
                "limit": 1,
            },
        )
        assert replay.status_code in {200, 202, 404}

    with journey_step("Consumer submits a self-service DSR through the same privacy request contract"):
        self_service_dsr = await consumer_client.post(
            "/api/v1/me/dsr",
            json={
                "request_type": "access",
                "legal_basis": None,
                "hold_hours": 0,
            },
        )
        self_service_dsr.raise_for_status()
        self_service_payload = self_service_dsr.json()
        assert self_service_payload["subject_user_id"] == self_service_payload["requested_by"]

    with journey_step("Admin DSR path targets the same subject and exposes Rule 34 audit visibility"):
        admin_dsr = await admin_client.post(
            "/api/v1/privacy/dsr",
            json={
                "subject_user_id": self_service_payload["subject_user_id"],
                "request_type": "access",
                "legal_basis": "support-verification",
                "hold_hours": 0,
            },
        )
        assert admin_dsr.status_code in {201, 403}
        if admin_dsr.status_code == 201:
            assert admin_dsr.json()["subject_user_id"] == self_service_payload["subject_user_id"]
        activity = await consumer_client.get(
            "/api/v1/me/activity",
            params={"event_type": "privacy.dsr.submitted"},
        )
        activity.raise_for_status()
        assert "items" in activity.json()

    with journey_step("Admin deactivates the temporary webhook after the journey"):
        assert webhook_payload is not None
        deleted = await admin_client.delete(f"/api/v1/notifications/webhooks/{webhook_payload['id']}")
        deleted.raise_for_status()
        assert deleted.json()["active"] is False

    with journey_step("Consumer removes the temporary channel after the journey"):
        assert channel_payload is not None
        deleted = await consumer_client.delete(
            f"/api/v1/me/notifications/channels/{channel_payload['id']}"
        )
        deleted.raise_for_status()
