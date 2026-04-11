from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from platform.accounts import email as email_helpers
from platform.accounts.events import (
    AccountsEventType,
    InvitationPayload,
    UserActivatedPayload,
    UserEmailVerifiedPayload,
    UserLifecyclePayload,
    UserRegisteredPayload,
    publish_accounts_event,
)
from platform.accounts.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidOrExpiredTokenError,
    InvitationAlreadyConsumedError,
    InvitationExpiredError,
    InvitationNotFoundError,
    InvitationRevokedError,
    RateLimitError,
    SelfRegistrationDisabledError,
)
from platform.accounts.models import (
    ApprovalDecision,
    Invitation,
    InvitationStatus,
    SignupSource,
    User,
    UserStatus,
)
from platform.accounts.repository import AccountsRepository
from platform.accounts.schemas import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    CreateInvitationRequest,
    InvitationDetailsResponse,
    InvitationResponse,
    PaginatedInvitationsResponse,
    PendingApprovalsResponse,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResendVerificationResponse,
    ResetMfaResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    UnlockResponse,
    UserLifecycleResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from platform.accounts.state_machine import validate_transition
from platform.auth.service import AuthService
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import AccountsSettings, PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import AuthorizationError, NotFoundError
from typing import Any
from uuid import UUID, uuid4


class AccountsService:
    def __init__(
        self,
        repo: AccountsRepository,
        redis: AsyncRedisClient,
        kafka_producer: EventProducer | None,
        auth_service: AuthService,
        settings: PlatformSettings | AccountsSettings,
        *,
        notification_client: Any | None = None,
    ) -> None:
        self.repo = repo
        self.redis = redis
        self.kafka_producer = kafka_producer
        self.auth_service = auth_service
        self.settings = settings.accounts if hasattr(settings, "accounts") else settings
        self.notification_client = notification_client

    async def register(
        self,
        request: RegisterRequest,
        *,
        correlation_id: UUID | None = None,
    ) -> RegisterResponse:
        if self.settings.signup_mode == "invite_only":
            raise SelfRegistrationDisabledError()

        existing_user = await self.repo.get_user_by_email(request.email)
        if existing_user is not None:
            return RegisterResponse()

        user = await self.repo.create_user(
            email=request.email,
            display_name=request.display_name,
            status=UserStatus.pending_verification,
            signup_source=SignupSource.self_registration,
        )
        await self.auth_service.create_user_credential(user.id, user.email, request.password)

        token = secrets.token_urlsafe(32)
        await self.repo.create_email_verification(
            user.id,
            self._hash_token(token),
            self._now() + timedelta(hours=self.settings.email_verify_ttl_hours),
        )
        await email_helpers.send_verification_email(
            user.id,
            user.email,
            token,
            user.display_name,
            self.notification_client,
        )
        await publish_accounts_event(
            self.kafka_producer,
            AccountsEventType.user_registered,
            UserRegisteredPayload(
                user_id=user.id,
                email=user.email,
                signup_source=user.signup_source,
            ),
            self._correlation(correlation_id),
        )
        return RegisterResponse()

    async def verify_email(
        self,
        request: VerifyEmailRequest,
        *,
        correlation_id: UUID | None = None,
    ) -> VerifyEmailResponse:
        verification = await self.repo.get_active_verification_by_token_hash(
            self._hash_token(request.token)
        )
        if verification is None or verification.expires_at < self._now():
            raise InvalidOrExpiredTokenError()

        user = await self.repo.get_user_for_update(verification.user_id)
        if user is None:
            raise InvalidOrExpiredTokenError()

        next_status = (
            UserStatus.pending_approval
            if self.settings.signup_mode == "admin_approval"
            else UserStatus.active
        )
        validate_transition(user.status, next_status)

        first_activation = next_status == UserStatus.active and user.activated_at is None
        now = self._now()
        update_fields: dict[str, object] = {"email_verified_at": now}
        if next_status == UserStatus.active:
            update_fields["activated_at"] = user.activated_at or now
        updated_user = await self.repo.update_user_status(user.id, next_status, **update_fields)
        await self.repo.consume_verification(verification.id)
        if next_status == UserStatus.pending_approval:
            await self.repo.create_approval_request(user.id, now)

        correlation = self._correlation(correlation_id)
        await publish_accounts_event(
            self.kafka_producer,
            AccountsEventType.user_email_verified,
            UserEmailVerifiedPayload(user_id=updated_user.id, email=updated_user.email),
            correlation,
        )
        if first_activation:
            await self._publish_activation(updated_user, correlation)
        return VerifyEmailResponse(user_id=updated_user.id, status=updated_user.status)

    async def resend_verification(
        self,
        request: ResendVerificationRequest,
    ) -> ResendVerificationResponse:
        user = await self.repo.get_user_by_email(request.email)
        if user is None or user.status != UserStatus.pending_verification:
            return ResendVerificationResponse()

        count = await self.repo.increment_resend_count(self.redis, user.id)
        if count > self.settings.resend_rate_limit:
            client = await self.redis._get_client()
            retry_after = int(await client.ttl(f"resend_verify:{user.id}") or 0)
            raise RateLimitError(retry_after)

        token = secrets.token_urlsafe(32)
        await self.repo.create_email_verification(
            user.id,
            self._hash_token(token),
            self._now() + timedelta(hours=self.settings.email_verify_ttl_hours),
        )
        await email_helpers.send_verification_email(
            user.id,
            user.email,
            token,
            user.display_name,
            self.notification_client,
        )
        return ResendVerificationResponse()

    async def get_pending_approvals(self, page: int, page_size: int) -> PendingApprovalsResponse:
        items, total = await self.repo.get_pending_approvals(page, page_size)
        return PendingApprovalsResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
            has_prev=page > 1,
        )

    async def approve_user(
        self,
        user_id: UUID,
        reviewer_id: UUID,
        reason: str | None,
        *,
        correlation_id: UUID | None = None,
    ) -> UserLifecycleResponse:
        user = await self.repo.get_user_for_update(user_id)
        if user is None:
            raise NotFoundError("USER_NOT_FOUND", "User not found")
        validate_transition(user.status, UserStatus.active)
        approval = await self.repo.get_approval_request_for_update(user_id)
        if approval is None:
            raise NotFoundError("APPROVAL_REQUEST_NOT_FOUND", "Approval request not found")

        first_activation = user.activated_at is None
        now = self._now()
        updated = await self.repo.update_user_status(
            user_id, UserStatus.active, activated_at=user.activated_at or now
        )
        approval.reviewer_id = reviewer_id
        approval.decision = ApprovalDecision.approved
        approval.decision_at = now
        approval.reason = reason
        correlation = self._correlation(correlation_id)
        await publish_accounts_event(
            self.kafka_producer,
            AccountsEventType.user_approved,
            UserLifecyclePayload(user_id=user_id, actor_id=reviewer_id, reason=reason),
            correlation,
        )
        if first_activation:
            await self._publish_activation(updated, correlation)
        return UserLifecycleResponse(user_id=updated.id, status=updated.status)

    async def reject_user(
        self,
        user_id: UUID,
        reviewer_id: UUID,
        reason: str,
        *,
        correlation_id: UUID | None = None,
    ) -> UserLifecycleResponse:
        user = await self.repo.get_user_for_update(user_id)
        if user is None:
            raise NotFoundError("USER_NOT_FOUND", "User not found")
        validate_transition(user.status, UserStatus.archived)
        approval = await self.repo.get_approval_request_for_update(user_id)
        if approval is None:
            raise NotFoundError("APPROVAL_REQUEST_NOT_FOUND", "Approval request not found")
        now = self._now()
        updated = await self.repo.update_user_status(
            user_id,
            UserStatus.archived,
            archived_at=now,
            archived_by=reviewer_id,
            deleted_at=now,
        )
        approval.reviewer_id = reviewer_id
        approval.decision = ApprovalDecision.rejected
        approval.decision_at = now
        approval.reason = reason
        await publish_accounts_event(
            self.kafka_producer,
            AccountsEventType.user_rejected,
            UserLifecyclePayload(user_id=user_id, actor_id=reviewer_id, reason=reason),
            self._correlation(correlation_id),
        )
        return UserLifecycleResponse(user_id=updated.id, status=updated.status)

    async def create_invitation(
        self,
        request: CreateInvitationRequest,
        inviter_id: UUID,
        *,
        correlation_id: UUID | None = None,
    ) -> InvitationResponse:
        if await self.repo.get_user_by_email(request.email) is not None:
            raise EmailAlreadyRegisteredError()

        token = secrets.token_urlsafe(32)
        invitation = await self.repo.create_invitation(
            inviter_id=inviter_id,
            invitee_email=request.email,
            token_hash=self._hash_token(token),
            roles_json=json.dumps([role.value for role in request.roles]),
            workspace_ids_json=json.dumps([str(item) for item in request.workspace_ids])
            if request.workspace_ids
            else None,
            message=request.message,
            expires_at=self._now() + timedelta(days=self.settings.invite_ttl_days),
        )
        await email_helpers.send_invitation_email(
            invitation.id,
            invitation.invitee_email,
            token,
            inviter_id,
            request.message,
            self.notification_client,
        )
        await publish_accounts_event(
            self.kafka_producer,
            AccountsEventType.invitation_created,
            InvitationPayload(
                invitation_id=invitation.id,
                invitee_email=invitation.invitee_email,
                inviter_id=invitation.inviter_id,
            ),
            self._correlation(correlation_id),
        )
        return self._invitation_response(invitation)

    async def get_invitation_details(self, token: str) -> InvitationDetailsResponse:
        invitation = await self.repo.get_invitation_by_token_hash(self._hash_token(token))
        if invitation is None:
            raise InvitationNotFoundError()
        self._ensure_invitation_pending(invitation, not_found=True)
        inviter = await self.repo.get_user_by_id(invitation.inviter_id)
        if inviter is None:
            raise InvitationNotFoundError()
        return InvitationDetailsResponse(
            invitee_email=invitation.invitee_email,
            inviter_display_name=inviter.display_name,
            roles=self.repo.deserialize_roles(invitation),
            message=invitation.invitee_message,
            expires_at=invitation.expires_at,
        )

    async def accept_invitation(
        self,
        request: AcceptInvitationRequest,
        *,
        correlation_id: UUID | None = None,
    ) -> AcceptInvitationResponse:
        invitation = await self.repo.get_invitation_by_token_hash(self._hash_token(request.token))
        if invitation is None:
            raise InvitationNotFoundError()
        self._ensure_invitation_pending(invitation)
        if await self.repo.get_user_by_email(invitation.invitee_email) is not None:
            raise EmailAlreadyRegisteredError()

        user = await self.repo.create_user(
            email=invitation.invitee_email,
            display_name=request.display_name,
            status=UserStatus.active,
            signup_source=SignupSource.invitation,
            invitation_id=invitation.id,
        )
        user.activated_at = self._now()
        await self.auth_service.create_user_credential(user.id, user.email, request.password)
        await self.auth_service.assign_user_roles(
            user.id,
            self.repo.deserialize_roles(invitation),
            self.repo.deserialize_workspace_ids(invitation),
        )
        await self.repo.consume_invitation(invitation.id, user.id)
        correlation = self._correlation(correlation_id)
        await publish_accounts_event(
            self.kafka_producer,
            AccountsEventType.invitation_accepted,
            InvitationPayload(
                invitation_id=invitation.id,
                invitee_email=invitation.invitee_email,
                inviter_id=invitation.inviter_id,
                user_id=user.id,
            ),
            correlation,
        )
        await self._publish_activation(user, correlation)
        return AcceptInvitationResponse(
            user_id=user.id,
            email=user.email,
            status=user.status,
            display_name=user.display_name,
        )

    async def revoke_invitation(
        self,
        invitation_id: UUID,
        requestor_id: UUID,
        *,
        is_superadmin: bool = False,
        correlation_id: UUID | None = None,
    ) -> None:
        invitation = await self.repo.get_invitation_by_id(invitation_id)
        if invitation is None:
            raise InvitationNotFoundError()
        if invitation.inviter_id != requestor_id and not is_superadmin:
            raise AuthorizationError("PERMISSION_DENIED", "Not allowed to revoke this invitation")
        self._ensure_invitation_pending(invitation)
        await self.repo.revoke_invitation(invitation_id, requestor_id)
        await publish_accounts_event(
            self.kafka_producer,
            AccountsEventType.invitation_revoked,
            InvitationPayload(
                invitation_id=invitation.id,
                invitee_email=invitation.invitee_email,
                inviter_id=invitation.inviter_id,
            ),
            self._correlation(correlation_id),
        )

    async def list_invitations(
        self,
        inviter_id: UUID,
        status: InvitationStatus | None,
        page: int,
        page_size: int,
    ) -> PaginatedInvitationsResponse:
        items, total = await self.repo.list_invitations_by_inviter(
            inviter_id, status, page, page_size
        )
        return PaginatedInvitationsResponse(
            items=[self._invitation_response(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
            has_prev=page > 1,
        )

    async def suspend_user(
        self,
        user_id: UUID,
        actor_id: UUID,
        reason: str,
    ) -> UserLifecycleResponse:
        return await self._transition_user(
            user_id,
            actor_id,
            UserStatus.suspended,
            AccountsEventType.user_suspended,
            reason,
            suspended_at=self._now(),
            suspended_by=actor_id,
            suspend_reason=reason,
        )

    async def reactivate_user(
        self,
        user_id: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> UserLifecycleResponse:
        return await self._transition_user(
            user_id,
            actor_id,
            UserStatus.active,
            AccountsEventType.user_reactivated,
            reason,
            suspended_at=None,
            suspended_by=None,
            suspend_reason=None,
            blocked_at=None,
            blocked_by=None,
            block_reason=None,
        )

    async def block_user(
        self,
        user_id: UUID,
        actor_id: UUID,
        reason: str,
    ) -> UserLifecycleResponse:
        return await self._transition_user(
            user_id,
            actor_id,
            UserStatus.blocked,
            AccountsEventType.user_blocked,
            reason,
            blocked_at=self._now(),
            blocked_by=actor_id,
            block_reason=reason,
        )

    async def unblock_user(
        self,
        user_id: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> UserLifecycleResponse:
        return await self._transition_user(
            user_id,
            actor_id,
            UserStatus.active,
            AccountsEventType.user_unblocked,
            reason,
            blocked_at=None,
            blocked_by=None,
            block_reason=None,
        )

    async def archive_user(
        self,
        user_id: UUID,
        actor_id: UUID,
        reason: str | None = None,
    ) -> UserLifecycleResponse:
        now = self._now()
        return await self._transition_user(
            user_id,
            actor_id,
            UserStatus.archived,
            AccountsEventType.user_archived,
            reason,
            archived_at=now,
            archived_by=actor_id,
            deleted_at=now,
        )

    async def reset_mfa(self, user_id: UUID, actor_id: UUID) -> ResetMfaResponse:
        if await self.repo.get_user_by_id(user_id) is None:
            raise NotFoundError("USER_NOT_FOUND", "User not found")
        cleared = await self.auth_service.reset_mfa(user_id)
        await publish_accounts_event(
            self.kafka_producer,
            AccountsEventType.user_mfa_reset,
            UserLifecyclePayload(user_id=user_id, actor_id=actor_id),
            self._correlation(None),
        )
        return ResetMfaResponse(user_id=user_id, mfa_cleared=cleared)

    async def reset_password(
        self,
        user_id: UUID,
        actor_id: UUID,
        request: ResetPasswordRequest,
    ) -> ResetPasswordResponse:
        if await self.repo.get_user_by_id(user_id) is None:
            raise NotFoundError("USER_NOT_FOUND", "User not found")
        await self.auth_service.initiate_password_reset(user_id, request.force_change_on_login)
        await publish_accounts_event(
            self.kafka_producer,
            AccountsEventType.user_password_reset_initiated,
            UserLifecyclePayload(user_id=user_id, actor_id=actor_id),
            self._correlation(None),
        )
        return ResetPasswordResponse(user_id=user_id, password_reset_initiated=True)

    async def unlock_user(self, user_id: UUID, actor_id: UUID) -> UnlockResponse:
        if await self.repo.get_user_by_id(user_id) is None:
            raise NotFoundError("USER_NOT_FOUND", "User not found")
        await self.auth_service.clear_lockout(user_id)
        del actor_id
        return UnlockResponse(user_id=user_id, unlocked=True)

    async def _transition_user(
        self,
        user_id: UUID,
        actor_id: UUID,
        to_status: UserStatus,
        event_type: AccountsEventType,
        reason: str | None,
        **status_fields: object,
    ) -> UserLifecycleResponse:
        user = await self.repo.get_user_for_update(user_id)
        if user is None:
            raise NotFoundError("USER_NOT_FOUND", "User not found")
        validate_transition(user.status, to_status)
        updated = await self.repo.update_user_status(user_id, to_status, **status_fields)
        if to_status in {UserStatus.suspended, UserStatus.blocked, UserStatus.archived}:
            await self.auth_service.invalidate_user_sessions(user_id)
        await publish_accounts_event(
            self.kafka_producer,
            event_type,
            UserLifecyclePayload(user_id=user_id, actor_id=actor_id, reason=reason),
            self._correlation(None),
        )
        return UserLifecycleResponse(user_id=updated.id, status=updated.status)

    async def _publish_activation(self, user: User, correlation: CorrelationContext) -> None:
        await publish_accounts_event(
            self.kafka_producer,
            AccountsEventType.user_activated,
            UserActivatedPayload(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
                signup_source=user.signup_source,
            ),
            correlation,
        )

    def _ensure_invitation_pending(
        self,
        invitation: Invitation,
        *,
        not_found: bool = False,
    ) -> None:
        if invitation.status == InvitationStatus.consumed:
            raise InvitationNotFoundError() if not_found else InvitationAlreadyConsumedError()
        if invitation.status == InvitationStatus.revoked:
            raise InvitationNotFoundError() if not_found else InvitationRevokedError()
        if invitation.expires_at < self._now() or invitation.status == InvitationStatus.expired:
            raise InvitationNotFoundError() if not_found else InvitationExpiredError()

    def _invitation_response(self, invitation: Invitation) -> InvitationResponse:
        return InvitationResponse(
            id=invitation.id,
            invitee_email=invitation.invitee_email,
            roles=self.repo.deserialize_roles(invitation),
            workspace_ids=self.repo.deserialize_workspace_ids(invitation),
            status=invitation.status,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
        )

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _correlation(correlation_id: UUID | None) -> CorrelationContext:
        return CorrelationContext(correlation_id=correlation_id or uuid4())

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)
