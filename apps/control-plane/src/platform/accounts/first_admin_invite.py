"""Enterprise first-admin setup invitation lifecycle for UPD-048 FR-010 through FR-016."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from platform.accounts import email as email_helpers
from platform.accounts.events import (
    AccountsEventType,
    FirstAdminInvitationPayload,
    SetupCompletedPayload,
    SetupStepCompletedPayload,
    publish_accounts_event,
)
from platform.accounts.exceptions import SetupTokenInvalidError
from platform.accounts.metrics import Counter, Histogram
from platform.accounts.models import TenantFirstAdminInvitation
from platform.accounts.schemas import TenantFirstAdminInviteValidationResponse
from platform.audit.service import AuditChainService
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.tenants.models import Tenant
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

accounts_first_admin_invitation_issued_total = Counter(
    "accounts_first_admin_invitation_issued_total",
    "Enterprise first-admin setup invitations issued.",
)
accounts_first_admin_invitation_resent_total = Counter(
    "accounts_first_admin_invitation_resent_total",
    "Enterprise first-admin setup invitations resent.",
)
accounts_first_admin_invitation_consumed_seconds = Histogram(
    "accounts_first_admin_invitation_consumed_seconds",
    "Latency from first-admin setup invitation issue to consume.",
)


class TenantFirstAdminInviteService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: PlatformSettings,
        producer: EventProducer | None = None,
        audit_chain: AuditChainService | None = None,
        notification_client: object | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.producer = producer
        self.audit_chain = audit_chain
        self.notification_client = notification_client

    async def issue(
        self,
        tenant_id: UUID,
        target_email: str,
        super_admin_id: UUID,
    ) -> tuple[TenantFirstAdminInvitation, str]:
        token = secrets.token_urlsafe(32)
        invitation = TenantFirstAdminInvitation(
            tenant_id=tenant_id,
            token_hash=self.hash_token(token),
            target_email=target_email.strip().lower(),
            expires_at=datetime.now(UTC)
            + timedelta(days=self.settings.SIGNUP_FIRST_ADMIN_INVITE_TTL_DAYS),
            created_by_super_admin_id=super_admin_id,
            setup_step_state={},
            mfa_required=True,
        )
        self.session.add(invitation)
        await self.session.flush()
        await email_helpers.send_invitation_email(
            invitation.id,
            invitation.target_email,
            token,
            super_admin_id,
            "Complete Enterprise tenant setup.",
            self.notification_client,
        )
        accounts_first_admin_invitation_issued_total.inc()
        await self._publish(
            AccountsEventType.first_admin_invitation_issued,
            FirstAdminInvitationPayload(
                tenant_id=tenant_id,
                target_email=invitation.target_email,
                super_admin_id=super_admin_id,
                invitation_id=invitation.id,
                expires_at=invitation.expires_at.isoformat(),
            ),
            tenant_id,
        )
        await self._append_audit(
            "accounts.first_admin_invitation.issued",
            tenant_id,
            {
                "invitation_id": str(invitation.id),
                "target_email": invitation.target_email,
                "super_admin_id": str(super_admin_id),
                "expires_at": invitation.expires_at.isoformat(),
            },
            actor_role="super_admin",
        )
        return invitation, token

    async def validate(self, token: str) -> TenantFirstAdminInviteValidationResponse:
        invitation = await self._active_by_token(token)
        tenant = await self.session.get(Tenant, invitation.tenant_id)
        if tenant is None:
            raise SetupTokenInvalidError()
        completed = sorted(
            key for key, value in (invitation.setup_step_state or {}).items() if bool(value)
        )
        return TenantFirstAdminInviteValidationResponse(
            valid=True,
            tenant_id=tenant.id,
            tenant_slug=tenant.slug,
            tenant_display_name=tenant.display_name,
            target_email=invitation.target_email,
            expires_at=invitation.expires_at,
            current_step=self.current_step(invitation),
            completed_steps=completed,
        )

    async def consume(self, token: str, user_id: UUID) -> TenantFirstAdminInvitation:
        invitation = await self._active_by_token(token)
        now = datetime.now(UTC)
        state = invitation.setup_step_state or {}
        invitation.consumed_at = now
        invitation.consumed_by_user_id = user_id
        invitation.setup_step_state = {**state, "done": True}
        await self.session.flush()
        accounts_first_admin_invitation_consumed_seconds.observe(
            max(0.0, (now - invitation.created_at).total_seconds())
        )
        workspace_payload = state.get("workspace_payload")
        workspace_id = (
            UUID(str(workspace_payload.get("workspace_id")))
            if isinstance(workspace_payload, dict) and workspace_payload.get("workspace_id")
            else None
        )
        invitations_payload = state.get("invitations_payload")
        invitations_sent_count = (
            int(invitations_payload.get("invitations_sent", 0))
            if isinstance(invitations_payload, dict)
            else 0
        )
        await self._publish(
            AccountsEventType.setup_completed,
            SetupCompletedPayload(
                tenant_id=invitation.tenant_id,
                user_id=user_id,
                first_workspace_id=workspace_id,
                invitations_sent_count=invitations_sent_count,
            ),
            invitation.tenant_id,
        )
        await self._append_audit(
            "accounts.setup.completed",
            invitation.tenant_id,
            {
                "invitation_id": str(invitation.id),
                "user_id": str(user_id),
                "first_workspace_id": str(workspace_id) if workspace_id else None,
                "invitations_sent_count": invitations_sent_count,
            },
            actor_role="tenant_admin",
        )
        return invitation

    async def resend(
        self,
        invitation_id: UUID,
        super_admin_id: UUID,
    ) -> tuple[TenantFirstAdminInvitation, str]:
        prior = await self.session.get(TenantFirstAdminInvitation, invitation_id)
        if prior is None:
            raise SetupTokenInvalidError()
        prior.prior_token_invalidated_at = datetime.now(UTC)
        fresh, token = await self.issue(prior.tenant_id, prior.target_email, super_admin_id)
        accounts_first_admin_invitation_resent_total.inc()
        await self._publish(
            AccountsEventType.first_admin_invitation_resent,
            FirstAdminInvitationPayload(
                tenant_id=prior.tenant_id,
                target_email=prior.target_email,
                super_admin_id=super_admin_id,
                prior_invitation_id=prior.id,
                new_invitation_id=fresh.id,
                prior_token_invalidated_at=prior.prior_token_invalidated_at.isoformat(),
            ),
            prior.tenant_id,
        )
        await self._append_audit(
            "accounts.first_admin_invitation.resent",
            prior.tenant_id,
            {
                "prior_invitation_id": str(prior.id),
                "new_invitation_id": str(fresh.id),
                "target_email": prior.target_email,
                "super_admin_id": str(super_admin_id),
                "prior_token_invalidated_at": prior.prior_token_invalidated_at.isoformat(),
            },
            actor_role="super_admin",
        )
        return fresh, token

    async def resend_for_tenant(
        self,
        tenant_id: UUID,
        super_admin_id: UUID,
    ) -> tuple[TenantFirstAdminInvitation, str]:
        result = await self.session.execute(
            select(TenantFirstAdminInvitation)
            .where(
                TenantFirstAdminInvitation.tenant_id == tenant_id,
                TenantFirstAdminInvitation.consumed_at.is_(None),
                TenantFirstAdminInvitation.prior_token_invalidated_at.is_(None),
            )
            .order_by(TenantFirstAdminInvitation.created_at.desc())
            .limit(1)
        )
        invitation = result.scalar_one_or_none()
        if invitation is None:
            raise SetupTokenInvalidError()
        return await self.resend(invitation.id, super_admin_id)

    async def record_step(
        self,
        token: str,
        step: str,
        payload: dict[str, object],
        *,
        user_id: UUID | None = None,
    ) -> TenantFirstAdminInvitation:
        invitation = await self._active_by_token(token)
        invitation.setup_step_state = {
            **(invitation.setup_step_state or {}),
            step: True,
            f"{step}_payload": payload,
        }
        await self.session.flush()
        await self._publish(
            AccountsEventType.setup_step_completed,
            SetupStepCompletedPayload(
                tenant_id=invitation.tenant_id,
                step=step,
                user_id=user_id,
            ),
            invitation.tenant_id,
        )
        await self._append_audit(
            "accounts.setup.step_completed",
            invitation.tenant_id,
            {
                "invitation_id": str(invitation.id),
                "step": step,
                "user_id": str(user_id) if user_id else None,
                **payload,
            },
        )
        return invitation

    async def _active_by_token(self, token: str) -> TenantFirstAdminInvitation:
        result = await self.session.execute(
            select(TenantFirstAdminInvitation).where(
                TenantFirstAdminInvitation.token_hash == self.hash_token(token)
            )
        )
        invitation = result.scalar_one_or_none()
        now = datetime.now(UTC)
        if (
            invitation is None
            or invitation.expires_at <= now
            or invitation.consumed_at is not None
            or invitation.prior_token_invalidated_at is not None
        ):
            raise SetupTokenInvalidError()
        return invitation

    @staticmethod
    def current_step(invitation: TenantFirstAdminInvitation) -> str:
        state = invitation.setup_step_state or {}
        for step in ("tos", "credentials", "mfa", "workspace", "invitations"):
            if not state.get(step):
                return step
        return "done"

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def _publish(
        self,
        event_type: AccountsEventType,
        payload: FirstAdminInvitationPayload | SetupCompletedPayload | SetupStepCompletedPayload,
        tenant_id: UUID,
    ) -> None:
        await publish_accounts_event(
            self.producer,
            event_type,
            payload,
            CorrelationContext(correlation_id=uuid4(), tenant_id=tenant_id),
        )

    async def _append_audit(
        self,
        event_type: str,
        tenant_id: UUID,
        payload: dict[str, object],
        *,
        actor_role: str | None = None,
    ) -> None:
        if self.audit_chain is None:
            return
        canonical_payload = {"tenant_id": str(tenant_id), **payload}
        canonical = json.dumps(
            canonical_payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        await self.audit_chain.append(
            uuid4(),
            "accounts.first_admin_invite",
            canonical,
            event_type=event_type,
            actor_role=actor_role,
            canonical_payload_json=canonical_payload,
            tenant_id=tenant_id,
        )
