from __future__ import annotations

from platform.billing.exceptions import NoActiveSubscriptionError
from platform.billing.subscriptions.models import Subscription
from platform.tenants.models import Tenant
from platform.workspaces.models import Workspace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ACTIVE_SUBSCRIPTION_STATUSES = ("trial", "active", "cancellation_pending")


class SubscriptionResolver:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve_active_subscription(self, workspace_id: UUID) -> Subscription:
        workspace = await self.session.get(Workspace, workspace_id)
        if workspace is None:
            raise NoActiveSubscriptionError(workspace_id)
        tenant = await self.session.get(Tenant, workspace.tenant_id)
        if tenant is None:
            raise NoActiveSubscriptionError(workspace_id)
        scope_type = "tenant" if tenant.kind == "enterprise" else "workspace"
        scope_id = tenant.id if scope_type == "tenant" else workspace.id
        result = await self.session.execute(
            select(Subscription)
            .where(
                Subscription.scope_type == scope_type,
                Subscription.scope_id == scope_id,
                Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
            )
            .order_by(Subscription.created_at.desc(), Subscription.id.desc())
            .limit(1)
        )
        subscription = result.scalar_one_or_none()
        if subscription is None:
            raise NoActiveSubscriptionError(workspace_id)
        return subscription
