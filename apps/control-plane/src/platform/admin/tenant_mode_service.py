from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.admin.audit_utils import actor_user_id, append_admin_audit
from platform.admin.events import (
    AdminEventType,
    TenantModeChangedPayload,
    publish_admin_event,
)
from platform.admin.two_person_auth_service import TwoPersonAuthService
from platform.audit.service import AuditChainService
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import AuthorizationError, ValidationError
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TenantMode = Literal["single", "multi"]
TENANT_MODE_UPGRADE_ACTION = "admin.tenant_mode.upgrade_to_multi"
TENANT_MODE_DOWNGRADE_ACTION = "admin.tenant_mode.downgrade_to_single"


class TenantModeService:
    def __init__(
        self,
        session: AsyncSession,
        two_person_auth: TwoPersonAuthService,
        audit_chain: AuditChainService,
        producer: EventProducer | None = None,
    ) -> None:
        self.session = session
        self.two_person_auth = two_person_auth
        self.audit_chain = audit_chain
        self.producer = producer

    async def upgrade_to_multi(
        self,
        *,
        actor: dict[str, Any],
        two_person_auth_token: str | None,
    ) -> dict[str, object]:
        await self._require_2pa(two_person_auth_token, TENANT_MODE_UPGRADE_ACTION)
        previous_mode = await self._get_mode()
        await self._set_mode("multi")
        await self._emit_change(previous_mode, "multi", actor)
        return {"previous_mode": previous_mode, "tenant_mode": "multi"}

    async def downgrade_to_single(
        self,
        *,
        actor: dict[str, Any],
        two_person_auth_token: str | None,
    ) -> dict[str, object]:
        await self._require_2pa(two_person_auth_token, TENANT_MODE_DOWNGRADE_ACTION)
        blocking_tenant_ids = await self._blocking_tenant_ids()
        if len(blocking_tenant_ids) > 1:
            raise ValidationError(
                "TENANT_MODE_DOWNGRADE_BLOCKED",
                "Remove extra tenants before downgrading to single-tenant mode",
                {"tenant_ids": [str(tenant_id) for tenant_id in blocking_tenant_ids]},
            )
        previous_mode = await self._get_mode()
        await self._set_mode("single")
        await self._emit_change(previous_mode, "single", actor)
        return {
            "previous_mode": previous_mode,
            "tenant_mode": "single",
            "blocking_tenant_ids": [str(tenant_id) for tenant_id in blocking_tenant_ids],
        }

    async def _require_2pa(self, token: str | None, action: str) -> None:
        if not token:
            raise AuthorizationError("TWO_PERSON_AUTH_REQUIRED", "2PA token is required")
        if not await self.two_person_auth.validate_token(token, action):
            raise AuthorizationError("TWO_PERSON_AUTH_INVALID", "Invalid or expired 2PA token")

    async def _get_mode(self) -> TenantMode:
        result = await self.session.execute(
            text(
                """
                SELECT value
                FROM platform_settings
                WHERE key = 'tenant_mode'
                  AND scope = 'global'
                  AND scope_id IS NULL
                LIMIT 1
                FOR UPDATE
                """
            )
        )
        value = result.scalar_one_or_none()
        if value in {"single", "multi"}:
            return cast(TenantMode, value)
        return "single"

    async def _set_mode(self, mode: TenantMode) -> None:
        result = await self.session.execute(
            text(
                """
                UPDATE platform_settings
                SET value = CAST(:value AS jsonb), updated_at = now()
                WHERE key = 'tenant_mode'
                  AND scope = 'global'
                  AND scope_id IS NULL
                """
            ),
            {"value": json.dumps(mode)},
        )
        if int(getattr(result, "rowcount", 0) or 0) > 0:
            return
        await self.session.execute(
            text(
                """
                INSERT INTO platform_settings (key, value, scope, scope_id)
                VALUES ('tenant_mode', CAST(:value AS jsonb), 'global', NULL)
                """
            ),
            {"value": json.dumps(mode)},
        )

    async def _blocking_tenant_ids(self) -> list[UUID]:
        result = await self.session.execute(
            text(
                """
                SELECT DISTINCT scope_id
                FROM platform_settings
                WHERE scope = 'tenant'
                  AND scope_id IS NOT NULL
                ORDER BY scope_id ASC
                """
            )
        )
        return [UUID(str(value)) for value in result.scalars().all()]

    async def _emit_change(
        self,
        previous_mode: TenantMode,
        new_mode: TenantMode,
        actor: dict[str, Any],
    ) -> None:
        changed_at = datetime.now(UTC)
        await append_admin_audit(
            self.audit_chain,
            event_type=AdminEventType.tenant_mode_changed.value,
            actor=actor,
            severity="critical",
            payload={
                "previous_mode": previous_mode,
                "new_mode": new_mode,
                "changed_at": changed_at.isoformat(),
            },
        )
        await publish_admin_event(
            self.producer,
            AdminEventType.tenant_mode_changed,
            TenantModeChangedPayload(
                previous_mode=previous_mode,
                new_mode=new_mode,
                actor_user_id=actor_user_id(actor),
                changed_at=changed_at,
            ),
            CorrelationContext(correlation_id=uuid4()),
        )
