from __future__ import annotations

from platform.me.schemas import UserNotificationPreferencesUpdateRequest
from platform.me.service import MeService
from platform.notifications.models import DeliveryMethod
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tests.unit.test_me_service_router import (
    AuditStub,
    AuthStub,
    ConsentStub,
    DSRStub,
    NotificationsStub,
)


def test_mandatory_notification_events_keep_at_least_one_channel() -> None:
    with pytest.raises(ValidationError):
        UserNotificationPreferencesUpdateRequest(per_channel_preferences={"security.login": []})
    assert UserNotificationPreferencesUpdateRequest(
        per_channel_preferences={"security.login": [DeliveryMethod.email.value]}
    ).per_channel_preferences == {"security.login": ["email"]}


@pytest.mark.asyncio
async def test_notification_preferences_round_trip_and_test_alert() -> None:
    user_id = uuid4()
    notifications = NotificationsStub(user_id)
    service = MeService(
        auth_service=AuthStub(user_id, uuid4(), uuid4()),
        consent_service=ConsentStub(user_id),
        dsr_service=DSRStub(user_id),
        notifications_service=notifications,
        audit_service=AuditStub(user_id),
    )

    updated = await service.update_notification_preferences(
        user_id,
        UserNotificationPreferencesUpdateRequest(
            delivery_method=DeliveryMethod.email,
            per_channel_preferences={"workspace.updated": [DeliveryMethod.email.value]},
            digest_mode={"email": "daily"},
            quiet_hours={"start_time": "22:00", "end_time": "07:00", "timezone": "UTC"},
        ),
    )
    tested = await service.test_notification(user_id, "workspace.updated")

    assert updated.delivery_method == DeliveryMethod.email
    assert notifications.repo.upserts[0]["digest_mode"] == {"email": "daily"}
    assert tested.event_type == "workspace.updated"
