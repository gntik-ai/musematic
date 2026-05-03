"""Suspension lifecycle service (UPD-050 T035).

Owns the ``account_suspensions`` aggregate. Provides:

- ``suspend(...)`` — auto + admin manual suspensions; records audit-chain
  entry and emits ``security.suspension_created``.
- ``lift(...)`` — super-admin lift with required reason; emits
  ``security.suspension_lifted`` and triggers a UPD-042 alert to the user.
- ``get_active_for_user(user_id)`` — used by the login path (T036) to
  refuse logins for suspended users.
- ``list_active(...)`` — admin queue listing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.audit.service import AuditChainService
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from platform.notifications.service import AlertService
from platform.security.abuse_prevention.events import (
    AbuseEventType,
    SuspensionCreatedPayload,
    SuspensionLiftedPayload,
    publish_abuse_event,
)
from platform.security.abuse_prevention.exceptions import SuspensionAlreadyLiftedError
from platform.security.abuse_prevention.metrics import (
    abuse_suspension_created_total,
    abuse_suspension_lifted_total,
)
from platform.security.abuse_prevention.models import AccountSuspension
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = get_logger(__name__)


class SuspensionService:
    """CRUD + state transitions for the ``account_suspensions`` aggregate."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        audit_chain: AuditChainService | None,
        event_producer: EventProducer | None,
        alert_service: AlertService | None,
    ) -> None:
        self._session = session
        self._audit = audit_chain
        self._producer = event_producer
        self._alerts = alert_service

    async def suspend(
        self,
        *,
        user_id: UUID,
        tenant_id: UUID,
        reason: str,
        evidence: dict[str, Any] | None = None,
        suspended_by: str = "system",
        suspended_by_user_id: UUID | None = None,
    ) -> AccountSuspension:
        """Create a suspension row and emit the matching events."""
        row = AccountSuspension(
            user_id=user_id,
            tenant_id=tenant_id,
            reason=reason,
            evidence_json=evidence or {},
            suspended_by=suspended_by,
            suspended_by_user_id=suspended_by_user_id,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.commit()

        abuse_suspension_created_total.labels(reason=reason).inc()

        canonical_payload: dict[str, object] = {
            "suspension_id": str(row.id),
            "user_id": str(user_id),
            "tenant_id": str(tenant_id),
            "reason": reason,
            "suspended_by": suspended_by,
            "suspended_by_user_id": (
                str(suspended_by_user_id)
                if suspended_by_user_id is not None
                else None
            ),
        }
        if self._audit is not None:
            canonical_bytes = json.dumps(
                canonical_payload, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            await self._audit.append(
                uuid4(),
                "abuse_prevention",
                canonical_bytes,
                event_type=AbuseEventType.suspension_created.value,
                actor_role=suspended_by,
                canonical_payload_json=canonical_payload,
                tenant_id=tenant_id,
            )
        await publish_abuse_event(
            self._producer,
            AbuseEventType.suspension_created,
            SuspensionCreatedPayload(
                suspension_id=str(row.id),
                user_id=str(user_id),
                reason=reason,
                evidence_summary=_evidence_summary(evidence),
                suspended_by=suspended_by,
                suspended_by_user_id=(
                    str(suspended_by_user_id)
                    if suspended_by_user_id is not None
                    else None
                ),
            ),
            CorrelationContext(correlation_id=uuid4(), tenant_id=tenant_id),
        )
        LOGGER.info(
            "security.suspension_created",
            extra={
                "suspension_id": str(row.id),
                "user_id": str(user_id),
                "tenant_id": str(tenant_id),
                "reason": reason,
                "suspended_by": suspended_by,
            },
        )
        return row

    async def lift(
        self,
        *,
        suspension_id: UUID,
        actor_user_id: UUID,
        reason: str,
    ) -> AccountSuspension:
        """Lift an active suspension. Raises if already lifted."""
        result = await self._session.execute(
            select(AccountSuspension).where(
                AccountSuspension.id == suspension_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            from platform.common.exceptions import NotFoundError

            raise NotFoundError(
                "suspension_not_found",
                "Suspension not found.",
            )
        if row.lifted_at is not None:
            raise SuspensionAlreadyLiftedError(suspension_id)

        await self._session.execute(
            update(AccountSuspension)
            .where(AccountSuspension.id == suspension_id)
            .values(
                lifted_at=datetime.now(tz=UTC),
                lifted_by_user_id=actor_user_id,
                lift_reason=reason,
            )
        )
        await self._session.commit()
        await self._session.refresh(row)

        abuse_suspension_lifted_total.inc()

        canonical_payload: dict[str, object] = {
            "suspension_id": str(suspension_id),
            "user_id": str(row.user_id),
            "tenant_id": str(row.tenant_id),
            "lifted_by_user_id": str(actor_user_id),
            "lift_reason": reason,
        }
        if self._audit is not None:
            canonical_bytes = json.dumps(
                canonical_payload, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            await self._audit.append(
                uuid4(),
                "abuse_prevention",
                canonical_bytes,
                event_type=AbuseEventType.suspension_lifted.value,
                actor_role="super_admin",
                canonical_payload_json=canonical_payload,
                tenant_id=row.tenant_id,
            )
        await publish_abuse_event(
            self._producer,
            AbuseEventType.suspension_lifted,
            SuspensionLiftedPayload(
                suspension_id=str(suspension_id),
                user_id=str(row.user_id),
                lifted_by_user_id=str(actor_user_id),
                lift_reason=reason,
            ),
            CorrelationContext(
                correlation_id=uuid4(), tenant_id=row.tenant_id
            ),
        )

        if self._alerts is not None:
            await self._alerts.create_admin_alert(
                user_id=row.user_id,
                alert_type="security.suspension_lifted",
                title="Your account has been reinstated",
                body=(
                    "Your account suspension has been lifted by platform staff. "
                    "You can now log in and resume normal use."
                ),
                urgency="medium",
                source_reference={
                    "kind": "security.suspension_lifted",
                    "suspension_id": str(suspension_id),
                },
            )

        LOGGER.info(
            "security.suspension_lifted",
            extra={
                "suspension_id": str(suspension_id),
                "user_id": str(row.user_id),
                "tenant_id": str(row.tenant_id),
                "lifted_by_user_id": str(actor_user_id),
            },
        )
        return row

    async def get_active_for_user(
        self, user_id: UUID
    ) -> AccountSuspension | None:
        """Return the active suspension row for a user, or None.

        The login path (T036) calls this on every login attempt; the
        partial index ``as_user_active_idx`` keeps the query cheap.
        """
        result = await self._session.execute(
            select(AccountSuspension)
            .where(AccountSuspension.user_id == user_id)
            .where(AccountSuspension.lifted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_active(
        self,
        *,
        status: str = "active",
        limit: int = 50,
    ) -> list[AccountSuspension]:
        stmt = select(AccountSuspension).order_by(
            AccountSuspension.suspended_at.desc()
        )
        if status == "active":
            stmt = stmt.where(AccountSuspension.lifted_at.is_(None))
        elif status == "lifted":
            stmt = stmt.where(AccountSuspension.lifted_at.is_not(None))
        # status='all' applies no additional filter
        result = await self._session.execute(stmt.limit(limit))
        return list(result.scalars())


def _evidence_summary(evidence: dict[str, Any] | None) -> str:
    if not evidence:
        return ""
    # A short rendering — enough for the event payload, not so much
    # that PII leaks into Kafka.
    return ", ".join(f"{k}={v}" for k, v in list(evidence.items())[:3])
