from __future__ import annotations

from platform.auth.events import (
    AUTH_EVENT_SCHEMAS,
    ApiKeyRotatedPayload,
    UserAuthenticatedPayload,
    publish_auth_event,
    register_auth_event_types,
)
from platform.common.events.registry import event_registry
from uuid import uuid4

from tests.auth_support import RecordingProducer


def test_register_auth_event_types_registers_all_schemas() -> None:
    register_auth_event_types()

    for event_type in AUTH_EVENT_SCHEMAS:
        assert event_registry.is_registered(event_type) is True


async def test_publish_auth_event_noops_without_producer() -> None:
    register_auth_event_types()

    await publish_auth_event(
        "auth.user.authenticated",
        UserAuthenticatedPayload(
            user_id=uuid4(),
            session_id=uuid4(),
            ip_address="127.0.0.1",
            device_info="pytest",
        ),
        uuid4(),
        None,
    )


async def test_publish_auth_event_uses_subject_as_key() -> None:
    register_auth_event_types()
    producer = RecordingProducer()
    service_account_id = uuid4()

    await publish_auth_event(
        "auth.apikey.rotated",
        ApiKeyRotatedPayload(service_account_id=service_account_id),
        uuid4(),
        producer,
    )

    assert producer.events[0]["topic"] == "auth.events"
    assert producer.events[0]["key"] == str(service_account_id)
    assert producer.events[0]["event_type"] == "auth.apikey.rotated"
