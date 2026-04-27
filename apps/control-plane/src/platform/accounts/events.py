from __future__ import annotations

from enum import StrEnum
from platform.accounts.models import SignupSource
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class AccountsEventType(StrEnum):
    user_registered = "accounts.user.registered"
    user_email_verified = "accounts.user.email_verified"
    user_profile_completed = "accounts.user.profile_completed"
    user_approved = "accounts.user.approved"
    user_rejected = "accounts.user.rejected"
    user_activated = "accounts.user.activated"
    user_suspended = "accounts.user.suspended"
    user_reactivated = "accounts.user.reactivated"
    user_blocked = "accounts.user.blocked"
    user_unblocked = "accounts.user.unblocked"
    user_archived = "accounts.user.archived"
    user_mfa_reset = "accounts.user.mfa_reset"
    user_password_reset_initiated = "accounts.user.password_reset_initiated"
    invitation_created = "accounts.invitation.created"
    invitation_accepted = "accounts.invitation.accepted"
    invitation_revoked = "accounts.invitation.revoked"


class UserRegisteredPayload(BaseModel):
    user_id: UUID
    email: str
    signup_source: SignupSource


class UserEmailVerifiedPayload(BaseModel):
    user_id: UUID
    email: str


class UserProfileCompletedPayload(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    locale: str | None = None
    timezone: str | None = None


class UserActivatedPayload(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    signup_source: SignupSource


class UserLifecyclePayload(BaseModel):
    user_id: UUID
    actor_id: UUID
    reason: str | None = None


class InvitationPayload(BaseModel):
    invitation_id: UUID
    invitee_email: str
    inviter_id: UUID
    user_id: UUID | None = None


ACCOUNTS_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    AccountsEventType.user_registered.value: UserRegisteredPayload,
    AccountsEventType.user_email_verified.value: UserEmailVerifiedPayload,
    AccountsEventType.user_profile_completed.value: UserProfileCompletedPayload,
    AccountsEventType.user_approved.value: UserLifecyclePayload,
    AccountsEventType.user_rejected.value: UserLifecyclePayload,
    AccountsEventType.user_activated.value: UserActivatedPayload,
    AccountsEventType.user_suspended.value: UserLifecyclePayload,
    AccountsEventType.user_reactivated.value: UserLifecyclePayload,
    AccountsEventType.user_blocked.value: UserLifecyclePayload,
    AccountsEventType.user_unblocked.value: UserLifecyclePayload,
    AccountsEventType.user_archived.value: UserLifecyclePayload,
    AccountsEventType.user_mfa_reset.value: UserLifecyclePayload,
    AccountsEventType.user_password_reset_initiated.value: UserLifecyclePayload,
    AccountsEventType.invitation_created.value: InvitationPayload,
    AccountsEventType.invitation_accepted.value: InvitationPayload,
    AccountsEventType.invitation_revoked.value: InvitationPayload,
}


def register_accounts_event_types() -> None:
    for event_type, schema in ACCOUNTS_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_accounts_event(
    producer: EventProducer | None,
    event_type: AccountsEventType | str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
    *,
    source: str = "platform.accounts",
) -> None:
    if producer is None:
        return

    event_name = event_type.value if isinstance(event_type, AccountsEventType) else event_type
    payload_dict = payload.model_dump(mode="json")
    subject_id = (
        payload_dict.get("user_id")
        or payload_dict.get("invitation_id")
        or str(correlation_ctx.correlation_id)
    )
    await producer.publish(
        topic="accounts.events",
        key=str(subject_id),
        event_type=event_name,
        payload=payload_dict,
        correlation_ctx=correlation_ctx,
        source=source,
    )
