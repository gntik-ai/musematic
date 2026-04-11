from __future__ import annotations

from platform.accounts.events import (
    ACCOUNTS_EVENT_SCHEMAS,
    AccountsEventType,
    InvitationPayload,
    UserActivatedPayload,
    publish_accounts_event,
    register_accounts_event_types,
)
from platform.accounts.models import SignupSource
from platform.common.events.envelope import CorrelationContext
from platform.common.events.registry import event_registry
from uuid import uuid4

import pytest
from pydantic import BaseModel

from tests.auth_support import RecordingProducer


class GenericPayload(BaseModel):
    value: str


def test_register_accounts_event_types_registers_every_schema() -> None:
    register_accounts_event_types()

    assert set(ACCOUNTS_EVENT_SCHEMAS) == {event.value for event in AccountsEventType}
    assert all(event_registry.is_registered(event.value) for event in AccountsEventType)


@pytest.mark.asyncio
async def test_publish_accounts_event_uses_user_id_as_key() -> None:
    producer = RecordingProducer()
    correlation = CorrelationContext(correlation_id=uuid4())
    payload = UserActivatedPayload(
        user_id=uuid4(),
        email="user@example.com",
        display_name="Jane Smith",
        signup_source=SignupSource.self_registration,
    )

    await publish_accounts_event(
        producer,
        AccountsEventType.user_activated,
        payload,
        correlation,
    )

    assert producer.events == [
        {
            "topic": "accounts.events",
            "key": str(payload.user_id),
            "event_type": AccountsEventType.user_activated.value,
            "payload": payload.model_dump(mode="json"),
            "correlation_ctx": correlation,
            "source": "platform.accounts",
        }
    ]


@pytest.mark.asyncio
async def test_publish_accounts_event_uses_invitation_id_or_correlation_fallback() -> None:
    producer = RecordingProducer()
    correlation = CorrelationContext(correlation_id=uuid4())
    invitation_payload = InvitationPayload(
        invitation_id=uuid4(),
        invitee_email="invitee@example.com",
        inviter_id=uuid4(),
    )

    await publish_accounts_event(
        producer,
        AccountsEventType.invitation_created.value,
        invitation_payload,
        correlation,
    )
    await publish_accounts_event(
        producer,
        "accounts.custom",
        GenericPayload(value="ok"),
        correlation,
    )
    await publish_accounts_event(None, "accounts.noop", GenericPayload(value="noop"), correlation)

    assert producer.events[0]["key"] == str(invitation_payload.invitation_id)
    assert producer.events[1]["key"] == str(correlation.correlation_id)
    assert producer.events[1]["event_type"] == "accounts.custom"
