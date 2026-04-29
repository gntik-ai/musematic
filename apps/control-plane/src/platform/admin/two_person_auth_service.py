from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.admin.two_person_auth_models import TwoPersonAuthRequest
from platform.common.config import PlatformSettings
from platform.common.exceptions import AuthorizationError, NotFoundError, ValidationError
from typing import Any
from uuid import UUID, uuid4

import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

TWO_PERSON_AUTH_TOKEN_TYPE = "admin_2pa"
DEFAULT_EXPIRY_MINUTES = 15


class TwoPersonAuthService:
    def __init__(self, session: AsyncSession, settings: PlatformSettings) -> None:
        self.session = session
        self.settings = settings

    async def initiate(
        self,
        action: str,
        payload: dict[str, object],
        initiator: UUID | dict[str, Any],
    ) -> TwoPersonAuthRequest:
        now = datetime.now(UTC)
        request = TwoPersonAuthRequest(
            request_id=uuid4(),
            action=action,
            payload=payload,
            initiator_id=_principal_id(initiator),
            created_at=now,
            expires_at=now + timedelta(minutes=DEFAULT_EXPIRY_MINUTES),
            consumed=False,
        )
        self.session.add(request)
        await self.session.flush()
        return request

    async def approve(self, request_id: UUID, approver: UUID | dict[str, Any]) -> str:
        approver_id = _principal_id(approver)
        request = await self._get_for_update(request_id)
        now = datetime.now(UTC)
        if request.initiator_id == approver_id:
            raise AuthorizationError(
                "TWO_PERSON_AUTH_SELF_APPROVAL",
                "Approver must be a different principal",
            )
        if request.expires_at <= now:
            raise ValidationError("TWO_PERSON_AUTH_EXPIRED", "2PA request expired")
        if request.rejected_at is not None:
            raise ValidationError("TWO_PERSON_AUTH_REJECTED", "2PA request has been rejected")
        if request.consumed:
            raise ValidationError("TWO_PERSON_AUTH_CONSUMED", "2PA request was already consumed")
        request.approved_by_id = approver_id
        request.approved_at = now
        await self.session.flush()
        return self._encode_token(request, approver_id)

    async def reject(
        self,
        request_id: UUID,
        approver: UUID | dict[str, Any],
        reason: str,
    ) -> None:
        request = await self._get_for_update(request_id)
        if request.consumed:
            raise ValidationError("TWO_PERSON_AUTH_CONSUMED", "2PA request was already consumed")
        if request.approved_at is not None:
            raise ValidationError("TWO_PERSON_AUTH_APPROVED", "2PA request was already approved")
        request.rejected_by_id = _principal_id(approver)
        request.rejected_at = datetime.now(UTC)
        request.rejection_reason = reason
        await self.session.flush()

    async def validate_token(self, token: str, action: str) -> bool:
        try:
            payload = jwt.decode(
                token,
                self.settings.auth.verification_key,
                algorithms=[self.settings.auth.jwt_algorithm],
            )
        except jwt.PyJWTError:
            return False
        if not isinstance(payload, dict) or payload.get("type") != TWO_PERSON_AUTH_TOKEN_TYPE:
            return False
        if payload.get("action") != action:
            return False
        try:
            request_id = UUID(str(payload["sub"]))
        except (KeyError, ValueError, TypeError):
            return False
        request = await self._get_for_update_or_none(request_id)
        if request is None:
            return False
        now = datetime.now(UTC)
        if (
            request.action != action
            or request.approved_at is None
            or request.rejected_at is not None
            or request.expires_at <= now
            or request.consumed
        ):
            return False
        request.consumed = True
        await self.session.flush()
        return True

    async def list_pending(self) -> list[TwoPersonAuthRequest]:
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(TwoPersonAuthRequest)
            .where(
                TwoPersonAuthRequest.approved_at.is_(None),
                TwoPersonAuthRequest.rejected_at.is_(None),
                TwoPersonAuthRequest.consumed.is_(False),
                TwoPersonAuthRequest.expires_at > now,
            )
            .order_by(TwoPersonAuthRequest.created_at.asc())
        )
        return list(result.scalars().all())

    async def get(self, request_id: UUID) -> TwoPersonAuthRequest:
        request = await self.session.get(TwoPersonAuthRequest, request_id)
        if request is None:
            raise NotFoundError("TWO_PERSON_AUTH_NOT_FOUND", "2PA request not found")
        return request

    async def expire_requests(self, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        result = await self.session.execute(
            update(TwoPersonAuthRequest)
            .where(
                TwoPersonAuthRequest.approved_at.is_(None),
                TwoPersonAuthRequest.rejected_at.is_(None),
                TwoPersonAuthRequest.consumed.is_(False),
                TwoPersonAuthRequest.expires_at <= now,
            )
            .values(rejected_at=now, rejection_reason="expired")
        )
        await self.session.flush()
        return int(getattr(result, "rowcount", 0) or 0)

    async def _get_for_update(self, request_id: UUID) -> TwoPersonAuthRequest:
        request = await self._get_for_update_or_none(request_id)
        if request is None:
            raise NotFoundError("TWO_PERSON_AUTH_NOT_FOUND", "2PA request not found")
        return request

    async def _get_for_update_or_none(self, request_id: UUID) -> TwoPersonAuthRequest | None:
        result = await self.session.execute(
            select(TwoPersonAuthRequest)
            .where(TwoPersonAuthRequest.request_id == request_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    def _encode_token(self, request: TwoPersonAuthRequest, approver_id: UUID) -> str:
        now = datetime.now(UTC)
        payload = {
            "type": TWO_PERSON_AUTH_TOKEN_TYPE,
            "sub": str(request.request_id),
            "action": request.action,
            "approved_by": str(approver_id),
            "iat": int(now.timestamp()),
            "exp": int(request.expires_at.timestamp()),
        }
        return jwt.encode(
            payload,
            self.settings.auth.signing_key,
            algorithm=self.settings.auth.jwt_algorithm,
        )


def _principal_id(principal: UUID | dict[str, Any]) -> UUID:
    if isinstance(principal, UUID):
        return principal
    return UUID(str(principal["sub"]))
