from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from platform.admin.impersonation_models import ImpersonationSession
from platform.admin.two_person_auth_service import TwoPersonAuthService
from platform.auth.schemas import RoleType
from platform.common.config import PlatformSettings
from platform.common.exceptions import AuthorizationError, NotFoundError, ValidationError
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import jwt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from platform.notifications.service import AlertService

IMPERSONATION_TTL_MINUTES = 30
IMPERSONATE_SUPERADMIN_ACTION = "admin.impersonation.superadmin"


class ImpersonationService:
    def __init__(
        self,
        session: AsyncSession,
        settings: PlatformSettings,
        two_person_auth: TwoPersonAuthService | None = None,
        notifications: AlertService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.two_person_auth = two_person_auth
        self.notifications = notifications

    async def start(
        self,
        impersonating_user: dict[str, Any],
        target_user: UUID,
        justification: str,
        *,
        two_person_auth_token: str | None = None,
    ) -> tuple[ImpersonationSession, str]:
        if len(justification.strip()) < 20:
            raise ValidationError(
                "IMPERSONATION_JUSTIFICATION_TOO_SHORT",
                "Impersonation requires a justification of at least 20 characters",
            )
        impersonating_user_id = UUID(str(impersonating_user["sub"]))
        if await self.get_active_session(impersonating_user_id) is not None:
            raise ValidationError(
                "IMPERSONATION_ALREADY_ACTIVE",
                "Nested impersonation sessions are not allowed",
            )
        target = await self._target_user(target_user)
        if target is None:
            raise NotFoundError("USER_NOT_FOUND", "Target user not found")
        target_roles = await self._roles(target_user)
        if RoleType.SUPERADMIN.value in {role["role"] for role in target_roles}:
            if self.two_person_auth is None or not two_person_auth_token:
                raise AuthorizationError(
                    "TWO_PERSON_AUTH_REQUIRED",
                    "Impersonating another super admin requires 2PA",
                )
            if not await self.two_person_auth.validate_token(
                two_person_auth_token,
                IMPERSONATE_SUPERADMIN_ACTION,
            ):
                raise AuthorizationError("TWO_PERSON_AUTH_INVALID", "Invalid 2PA token")

        now = datetime.now(UTC)
        session = ImpersonationSession(
            session_id=uuid4(),
            impersonating_user_id=impersonating_user_id,
            effective_user_id=target_user,
            justification=justification,
            started_at=now,
            expires_at=now + timedelta(minutes=IMPERSONATION_TTL_MINUTES),
        )
        self.session.add(session)
        await self.session.flush()
        await self._notify_impersonated_user(target_user, impersonating_user_id, session.session_id)
        token = self._issue_token(impersonating_user, target, target_roles, session)
        return session, token

    async def end(self, session_id: UUID, end_reason: str) -> None:
        session = await self.session.get(ImpersonationSession, session_id)
        if session is None:
            raise NotFoundError("IMPERSONATION_NOT_FOUND", "Impersonation session not found")
        if session.ended_at is None:
            session.ended_at = datetime.now(UTC)
            session.end_reason = end_reason
            await self._notify_impersonation_ended(
                session.effective_user_id,
                session.impersonating_user_id,
                session.session_id,
                end_reason,
            )
            await self.session.flush()

    async def get_active_session(self, impersonating_user_id: UUID) -> ImpersonationSession | None:
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(ImpersonationSession)
            .where(
                ImpersonationSession.impersonating_user_id == impersonating_user_id,
                ImpersonationSession.ended_at.is_(None),
                ImpersonationSession.expires_at > now,
            )
            .order_by(ImpersonationSession.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def expire_sessions(self, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        result = await self.session.execute(
            select(ImpersonationSession)
            .where(
                ImpersonationSession.ended_at.is_(None),
                ImpersonationSession.expires_at <= now,
            )
            .with_for_update()
        )
        expired = list(result.scalars().all())
        for session in expired:
            session.ended_at = now
            session.end_reason = "expired"
            await self._notify_impersonation_ended(
                session.effective_user_id,
                session.impersonating_user_id,
                session.session_id,
                "expired",
            )
        await self.session.flush()
        return len(expired)

    async def _target_user(self, user_id: UUID) -> dict[str, Any] | None:
        result = await self.session.execute(
            text(
                """
                SELECT id, email, COALESCE(username, display_name, email) AS username
                FROM users
                WHERE id = :user_id
                  AND deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
        row = result.mappings().first()
        return dict(row) if row is not None else None

    async def _roles(self, user_id: UUID) -> list[dict[str, Any]]:
        result = await self.session.execute(
            text(
                """
                SELECT role, workspace_id
                FROM user_roles
                WHERE user_id = :user_id
                ORDER BY role ASC
                """
            ),
            {"user_id": user_id},
        )
        return [
            {
                "role": row.role,
                "workspace_id": None if row.workspace_id is None else row.workspace_id,
            }
            for row in result
        ]

    async def _notify_impersonated_user(
        self,
        target_user_id: UUID,
        impersonating_user_id: UUID,
        session_id: UUID,
    ) -> None:
        source_reference = {
            "type": "admin_impersonation",
            "session_id": str(session_id),
            "impersonating_user_id": str(impersonating_user_id),
        }
        if self.notifications is not None:
            await self.notifications.create_admin_alert(
                user_id=target_user_id,
                alert_type="admin_impersonation_started",
                title="Admin impersonation started",
                body="A super admin started an impersonation session for your account.",
                urgency="critical",
                source_reference=source_reference,
            )
            return
        await self._insert_user_alert(
            target_user_id,
            source_reference,
            "admin_impersonation_started",
            "Admin impersonation started",
            "A super admin started an impersonation session for your account.",
        )

    async def _notify_impersonation_ended(
        self,
        target_user_id: UUID,
        impersonating_user_id: UUID,
        session_id: UUID,
        end_reason: str,
    ) -> None:
        source_reference = {
            "type": "admin_impersonation",
            "session_id": str(session_id),
            "impersonating_user_id": str(impersonating_user_id),
            "end_reason": end_reason,
        }
        if self.notifications is not None:
            await self.notifications.create_admin_alert(
                user_id=target_user_id,
                alert_type="admin_impersonation_ended",
                title="Admin impersonation ended",
                body="The admin impersonation session for your account has ended.",
                urgency="high",
                source_reference=source_reference,
            )
            return
        await self._insert_user_alert(
            target_user_id,
            source_reference,
            "admin_impersonation_ended",
            "Admin impersonation ended",
            "The admin impersonation session for your account has ended.",
            urgency="high",
        )

    async def _insert_user_alert(
        self,
        target_user_id: UUID,
        source_reference: dict[str, str],
        alert_type: str,
        title: str,
        body: str,
        *,
        urgency: str = "critical",
    ) -> None:
        await self.session.execute(
            text(
                """
                INSERT INTO user_alerts (
                    user_id,
                    interaction_id,
                    source_reference,
                    alert_type,
                    title,
                    body,
                    urgency,
                    read
                )
                VALUES (
                    :user_id,
                    NULL,
                    CAST(:source_reference AS jsonb),
                    :alert_type,
                    :title,
                    :body,
                    :urgency,
                    false
                )
                """
            ),
            {
                "user_id": target_user_id,
                "source_reference": json.dumps(source_reference),
                "alert_type": alert_type,
                "title": title,
                "body": body,
                "urgency": urgency,
            },
        )

    def _issue_token(
        self,
        impersonating_user: dict[str, Any],
        target: dict[str, Any],
        target_roles: list[dict[str, Any]],
        session: ImpersonationSession,
    ) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(target["id"]),
            "email": str(target["email"]),
            "roles": [
                {
                    "role": str(role["role"]),
                    "workspace_id": (
                        None if role.get("workspace_id") is None else str(role.get("workspace_id"))
                    ),
                }
                for role in target_roles
            ],
            "session_id": str(impersonating_user.get("session_id") or uuid4()),
            "iat": int(now.timestamp()),
            "exp": int(min(session.expires_at, now + timedelta(minutes=30)).timestamp()),
            "type": "access",
            "identity_type": "user",
            "impersonation_session_id": str(session.session_id),
            "impersonation_user_id": str(session.impersonating_user_id),
            "effective_user_id": str(session.effective_user_id),
        }
        return jwt.encode(
            payload,
            self.settings.auth.signing_key,
            algorithm=self.settings.auth.jwt_algorithm,
        )
