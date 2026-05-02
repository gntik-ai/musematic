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
    signup_completed = "accounts.signup.completed"
    first_admin_invitation_issued = "accounts.first_admin_invitation.issued"
    first_admin_invitation_resent = "accounts.first_admin_invitation.resent"
    setup_step_completed = "accounts.setup.step_completed"
    setup_completed = "accounts.setup.completed"
    cross_tenant_invitation_accepted = "accounts.cross_tenant_invitation.accepted"
    onboarding_step_advanced = "accounts.onboarding.step_advanced"
    onboarding_dismissed = "accounts.onboarding.dismissed"
    onboarding_relaunched = "accounts.onboarding.relaunched"


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


class SignupCompletedPayload(BaseModel):
    user_id: UUID
    email: str
    workspace_id: UUID | None = None
    subscription_id: UUID | None = None
    signup_method: str = "email"


class FirstAdminInvitationPayload(BaseModel):
    tenant_id: UUID
    target_email: str
    super_admin_id: UUID
    invitation_id: UUID | None = None
    expires_at: str | None = None
    prior_invitation_id: UUID | None = None
    new_invitation_id: UUID | None = None
    prior_token_invalidated_at: str | None = None


class SetupStepCompletedPayload(BaseModel):
    tenant_id: UUID
    step: str
    user_id: UUID | None = None


class SetupCompletedPayload(BaseModel):
    tenant_id: UUID
    user_id: UUID
    first_workspace_id: UUID | None = None
    invitations_sent_count: int = 0


class CrossTenantInvitationAcceptedPayload(BaseModel):
    default_tenant_user_id: UUID | None = None
    enterprise_tenant_id: UUID
    enterprise_user_id: UUID
    email: str


class OnboardingStepAdvancedPayload(BaseModel):
    user_id: UUID
    from_step: str
    to_step: str


class OnboardingDismissedPayload(BaseModel):
    user_id: UUID
    dismissed_at_step: str


class OnboardingRelaunchedPayload(BaseModel):
    user_id: UUID
    from_step: str


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
    AccountsEventType.signup_completed.value: SignupCompletedPayload,
    AccountsEventType.first_admin_invitation_issued.value: FirstAdminInvitationPayload,
    AccountsEventType.first_admin_invitation_resent.value: FirstAdminInvitationPayload,
    AccountsEventType.setup_step_completed.value: SetupStepCompletedPayload,
    AccountsEventType.setup_completed.value: SetupCompletedPayload,
    AccountsEventType.cross_tenant_invitation_accepted.value: CrossTenantInvitationAcceptedPayload,
    AccountsEventType.onboarding_step_advanced.value: OnboardingStepAdvancedPayload,
    AccountsEventType.onboarding_dismissed.value: OnboardingDismissedPayload,
    AccountsEventType.onboarding_relaunched.value: OnboardingRelaunchedPayload,
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
