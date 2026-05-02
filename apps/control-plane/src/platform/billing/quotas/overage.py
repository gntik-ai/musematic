from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.audit.service import AuditChainService
from platform.billing.exceptions import NoActiveSubscriptionError
from platform.billing.metrics import metrics
from platform.billing.plans.models import PlanVersion
from platform.billing.quotas.models import OverageAuthorization, UsageRecord
from platform.billing.subscriptions.models import Subscription
from platform.billing.subscriptions.resolver import SubscriptionResolver
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession


class OverageService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        resolver: SubscriptionResolver | None = None,
        execution_service: Any | None = None,
        audit_chain: AuditChainService | None = None,
        producer: EventProducer | None = None,
    ) -> None:
        self.session = session
        self.resolver = resolver or SubscriptionResolver(session)
        self.execution_service = execution_service
        self.audit_chain = audit_chain
        self.producer = producer

    async def authorize(
        self,
        workspace_id: UUID,
        billing_period_start: datetime | None,
        max_overage_eur: Decimal | None,
        authorising_user_id: UUID,
    ) -> OverageAuthorization:
        subscription = await self.resolver.resolve_active_subscription(workspace_id)
        period_start = billing_period_start or subscription.current_period_start
        statement = (
            insert(OverageAuthorization)
            .values(
                tenant_id=subscription.tenant_id,
                workspace_id=workspace_id,
                subscription_id=subscription.id,
                billing_period_start=period_start,
                billing_period_end=subscription.current_period_end,
                authorized_by_user_id=authorising_user_id,
                max_overage_eur=max_overage_eur,
            )
            .on_conflict_do_nothing(
                constraint="overage_authorizations_workspace_period_unique",
            )
            .returning(OverageAuthorization)
        )
        result = await self.session.execute(statement)
        authorization = result.scalar_one_or_none()
        if authorization is None:
            authorization = await self._get_for_period(workspace_id, period_start)
            if authorization is None:
                raise NoActiveSubscriptionError(workspace_id)
            if authorization.revoked_at is not None:
                authorization.revoked_at = None
                authorization.revoked_by_user_id = None
                authorization.max_overage_eur = max_overage_eur
                await self.session.flush()
        else:
            await self.session.flush()
        await self._resume_paused_executions(workspace_id, period_start)
        await self._publish_event(
            subscription,
            "billing.overage.authorized",
            {
                "workspace_id": str(workspace_id),
                "authorization_id": str(authorization.id),
                "billing_period_start": period_start.isoformat(),
                "max_overage_eur": None if max_overage_eur is None else str(max_overage_eur),
                "authorized_by_user_id": str(authorising_user_id),
            },
        )
        metrics.record_overage_authorize("authorized")
        return authorization

    async def revoke(self, authorization_id: UUID, revoking_user_id: UUID) -> OverageAuthorization:
        result = await self.session.execute(
            update(OverageAuthorization)
            .where(OverageAuthorization.id == authorization_id)
            .values(
                revoked_at=datetime.now(UTC),
                revoked_by_user_id=revoking_user_id,
            )
            .returning(OverageAuthorization)
        )
        authorization = result.scalar_one_or_none()
        if authorization is None:
            raise NoActiveSubscriptionError(authorization_id)
        await self.session.flush()
        subscription = await self.session.get(Subscription, authorization.subscription_id)
        if subscription is not None:
            await self._publish_event(
                subscription,
                "billing.overage.revoked",
                {
                    "workspace_id": str(authorization.workspace_id),
                    "authorization_id": str(authorization.id),
                    "revoked_by_user_id": str(revoking_user_id),
                },
            )
        metrics.record_overage_authorize("revoked")
        return authorization

    async def is_authorized_for_period(
        self,
        workspace_id: UUID,
        billing_period_start: datetime,
    ) -> bool:
        authorization = await self._get_for_period(workspace_id, billing_period_start)
        return authorization is not None and authorization.revoked_at is None

    async def current_overage_eur(
        self,
        subscription_id: UUID,
        billing_period_start: datetime,
    ) -> Decimal:
        subscription = await self.session.get(Subscription, subscription_id)
        if subscription is None:
            return Decimal("0")
        version = await self.session.scalar(
            select(PlanVersion).where(
                PlanVersion.plan_id == subscription.plan_id,
                PlanVersion.version == subscription.plan_version,
            )
        )
        if version is None:
            return Decimal("0")
        minutes = await self.session.scalar(
            select(func.coalesce(func.sum(UsageRecord.quantity), 0)).where(
                UsageRecord.subscription_id == subscription_id,
                UsageRecord.period_start == billing_period_start,
                UsageRecord.metric == "minutes",
                UsageRecord.is_overage.is_(True),
            )
        )
        return Decimal(minutes or 0) * Decimal(version.overage_price_per_minute)

    async def _get_for_period(
        self,
        workspace_id: UUID,
        billing_period_start: datetime,
    ) -> OverageAuthorization | None:
        result = await self.session.execute(
            select(OverageAuthorization)
            .where(
                OverageAuthorization.workspace_id == workspace_id,
                OverageAuthorization.billing_period_start == billing_period_start,
            )
            .order_by(OverageAuthorization.authorized_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _resume_paused_executions(
        self,
        workspace_id: UUID,
        billing_period_start: datetime,
    ) -> None:
        if self.execution_service is None:
            return
        resume = getattr(self.execution_service, "resume_paused_quota_exceeded", None)
        if callable(resume):
            await resume(workspace_id, billing_period_start)

    async def _publish_event(
        self,
        subscription: Subscription,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        if self.producer is None:
            return
        workspace_id = subscription.scope_id if subscription.scope_type == "workspace" else None
        await self.producer.publish(
            "billing.lifecycle",
            str(subscription.tenant_id),
            event_type,
            payload,
            CorrelationContext(
                correlation_id=uuid4(),
                tenant_id=subscription.tenant_id,
                workspace_id=workspace_id,
            ),
            "billing.overage",
        )
