from __future__ import annotations

from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.common.events.registry import event_registry
from platform.notifications.dependencies import (
    build_notifications_service,
    get_notifications_service,
)
from platform.notifications.events import (
    AlertCreatedPayload,
    AlertReadPayload,
    NotificationsEventType,
    publish_alert_created,
    publish_alert_read,
    register_notifications_event_types,
)
from platform.notifications.exceptions import AlertAuthorizationError, AlertNotFoundError
from platform.notifications.service import AlertService
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from tests.auth_support import RecordingProducer


@pytest.mark.asyncio
async def test_dependencies_build_service_and_get_dependency() -> None:
    settings = SimpleNamespace(notifications=SimpleNamespace())
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={"redis": object(), "kafka": None},
            )
        )
    )
    session = object()
    workspaces_service = object()

    built = build_notifications_service(
        session=session,  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
        redis_client=request.app.state.clients["redis"],  # type: ignore[arg-type]
        producer=None,
        workspaces_service=workspaces_service,  # type: ignore[arg-type]
    )
    resolved = await get_notifications_service(
        request,
        session=session,  # type: ignore[arg-type]
        workspaces_service=workspaces_service,  # type: ignore[arg-type]
    )

    assert isinstance(built, AlertService)
    assert isinstance(resolved, AlertService)


@pytest.mark.asyncio
async def test_notifications_events_register_and_publish_helpers() -> None:
    register_notifications_event_types()
    assert event_registry.is_registered(NotificationsEventType.alert_created.value) is True
    assert event_registry.is_registered(NotificationsEventType.alert_read.value) is True

    producer = RecordingProducer()
    correlation = CorrelationContext(correlation_id=uuid4())
    created_payload = AlertCreatedPayload(
        id=uuid4(),
        user_id=uuid4(),
        alert_type="attention_request",
        title="Attention requested",
        body="Review needed",
        urgency="high",
        read=False,
        interaction_id=None,
        source_reference={"type": "attention_request", "id": str(uuid4())},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    read_payload = AlertReadPayload(
        alert_id=uuid4(), user_id=created_payload.user_id, unread_count=1
    )

    await publish_alert_created(producer, created_payload, correlation)
    await publish_alert_read(producer, read_payload, correlation)
    await publish_alert_created(None, created_payload, correlation)

    assert [event["event_type"] for event in producer.events] == [
        "notifications.alert_created",
        "notifications.alert_read",
    ]
    assert producer.events[0]["topic"] == "notifications.alerts"


def test_notifications_exceptions_and_schema_validator() -> None:
    missing = AlertNotFoundError("alert-1")
    forbidden = AlertAuthorizationError()

    assert missing.code == "ALERT_NOT_FOUND"
    assert forbidden.code == "ALERT_FORBIDDEN"

    from platform.notifications.schemas import UserAlertSettingsUpdate

    with pytest.raises(ValidationError, match="webhook_url is required"):
        UserAlertSettingsUpdate(
            state_transitions=["any_to_failed"],
            delivery_method="webhook",
            webhook_url=None,
        )
