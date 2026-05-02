from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from platform.billing.quotas.models import UsageRecord
from platform.billing.subscriptions.models import Subscription
from platform.common.tenant_context import current_tenant
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession


class UsageRepository:
    def __init__(self, session: AsyncSession, redis_client: Any | None = None) -> None:
        self.session = session
        self.redis_client = redis_client

    async def increment(
        self,
        subscription_id: UUID,
        period_start: datetime,
        metric: str,
        quantity: Decimal,
        is_overage: bool,
        *,
        workspace_id: UUID | None = None,
        period_end: datetime | None = None,
        tenant_id: UUID | None = None,
    ) -> Decimal:
        subscription = await self.session.get(Subscription, subscription_id)
        if subscription is None:
            raise ValueError(f"subscription {subscription_id} was not found")
        resolved_workspace_id = workspace_id or subscription.scope_id
        resolved_tenant_id = tenant_id or subscription.tenant_id or _tenant_id()
        resolved_period_end = period_end or subscription.current_period_end
        statement = (
            insert(UsageRecord)
            .values(
                tenant_id=resolved_tenant_id,
                workspace_id=resolved_workspace_id,
                subscription_id=subscription_id,
                metric=metric,
                period_start=period_start,
                period_end=resolved_period_end,
                quantity=quantity,
                is_overage=is_overage,
            )
            .on_conflict_do_update(
                constraint="usage_records_unique_aggregate",
                set_={
                    "quantity": UsageRecord.quantity + quantity,
                    "period_end": resolved_period_end,
                },
            )
            .returning(UsageRecord.quantity)
        )
        result = await self.session.execute(statement)
        await self.session.flush()
        await self.invalidate(subscription_id, period_start)
        return Decimal(result.scalar_one())

    async def get_current_usage(
        self,
        subscription_id: UUID,
        period_start: datetime,
    ) -> dict[str, Decimal]:
        result = await self.session.execute(
            select(UsageRecord.metric, UsageRecord.quantity)
            .where(
                UsageRecord.subscription_id == subscription_id,
                UsageRecord.period_start == period_start,
                UsageRecord.is_overage.is_(False),
            )
            .order_by(UsageRecord.metric.asc())
        )
        totals: dict[str, Decimal] = {"executions": Decimal("0"), "minutes": Decimal("0")}
        for metric, quantity in result.all():
            totals[str(metric)] = Decimal(quantity)
        return totals

    async def get_period_history(
        self,
        subscription_id: UUID,
        limit: int = 12,
    ) -> list[UsageRecord]:
        result = await self.session.execute(
            select(UsageRecord)
            .where(UsageRecord.subscription_id == subscription_id)
            .order_by(UsageRecord.period_start.desc(), UsageRecord.metric.asc())
            .limit(limit * 2)
        )
        return list(result.scalars().all())

    async def invalidate(self, subscription_id: UUID, period_start: datetime) -> None:
        if self.redis_client is None:
            return
        usage_key = f"quota:usage:{subscription_id}:{period_start.isoformat()}"
        delete = getattr(self.redis_client, "delete", None)
        if callable(delete):
            await delete(usage_key)
        client = getattr(self.redis_client, "client", None)
        if client is not None and hasattr(client, "publish"):
            await client.publish(
                "billing:quota:invalidate",
                json.dumps(
                    {
                        "subscription_id": str(subscription_id),
                        "period_start": period_start.isoformat(),
                    }
                ),
            )


def _tenant_id() -> UUID:
    tenant = current_tenant.get(None)
    if tenant is None:
        raise RuntimeError("tenant context required for usage writes")
    return tenant.id
