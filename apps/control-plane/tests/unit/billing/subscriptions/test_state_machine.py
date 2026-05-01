from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.billing.exceptions import ConcurrentLifecycleActionError, SubscriptionScopeError
from platform.billing.plans.models import Plan, PlanVersion
from platform.billing.subscriptions.models import Subscription
from platform.billing.subscriptions.service import SubscriptionService
from platform.tenants.models import Tenant
from platform.workspaces.models import Workspace
from typing import Any
from uuid import UUID, uuid4

import pytest


def _period() -> tuple[datetime, datetime]:
    start = datetime(2026, 5, 1, tzinfo=UTC)
    return start, start + timedelta(days=30)


def _subscription(status: str = "active", *, cancel_at_period_end: bool = False) -> Subscription:
    start, end = _period()
    return Subscription(
        id=uuid4(),
        tenant_id=uuid4(),
        scope_type="workspace",
        scope_id=uuid4(),
        plan_id=uuid4(),
        plan_version=1,
        status=status,
        current_period_start=start,
        current_period_end=end,
        cancel_at_period_end=cancel_at_period_end,
    )


class _Subscriptions:
    def __init__(self, subscription: Subscription | None = None) -> None:
        self.subscription = subscription
        self.created: list[Subscription] = []

    async def get_by_id(self, subscription_id: UUID) -> Subscription | None:
        if self.subscription is None or self.subscription.id != subscription_id:
            return None
        return self.subscription

    async def get_by_scope(self, scope_type: str, scope_id: UUID) -> Subscription | None:
        if (
            self.subscription is not None
            and self.subscription.scope_type == scope_type
            and self.subscription.scope_id == scope_id
        ):
            return self.subscription
        return None

    async def set_cancel_at_period_end(
        self,
        subscription_id: UUID,
        cancel_at_period_end: bool,
    ) -> Subscription | None:
        subscription = await self.get_by_id(subscription_id)
        if subscription is None:
            return None
        subscription.cancel_at_period_end = cancel_at_period_end
        subscription.status = "cancellation_pending" if cancel_at_period_end else "active"
        return subscription

    async def update_status(self, subscription_id: UUID, status: str) -> Subscription | None:
        subscription = await self.get_by_id(subscription_id)
        if subscription is None:
            return None
        subscription.status = status
        if status == "canceled":
            subscription.cancel_at_period_end = False
        return subscription

    async def update_plan_pinning(
        self,
        subscription_id: UUID,
        **kwargs: Any,
    ) -> Subscription | None:
        subscription = await self.get_by_id(subscription_id)
        if subscription is None:
            return None
        for key, value in kwargs.items():
            if value is not None:
                setattr(subscription, key, value)
        return subscription

    async def create(self, **kwargs: Any) -> Subscription:
        subscription = Subscription(id=uuid4(), **kwargs)
        self.subscription = subscription
        self.created.append(subscription)
        return subscription


class _Plans:
    def __init__(self) -> None:
        self.plan = Plan(
            id=uuid4(),
            slug="free",
            display_name="Free",
            tier="free",
            description=None,
            is_public=True,
            is_active=True,
            allowed_model_tier="cheap_only",
        )
        self.version = PlanVersion(
            id=uuid4(),
            plan_id=self.plan.id,
            version=1,
            price_monthly=Decimal("0.00"),
            executions_per_day=50,
            executions_per_month=100,
            minutes_per_day=30,
            minutes_per_month=100,
            max_workspaces=1,
            max_agents_per_workspace=5,
            max_users_per_workspace=3,
            overage_price_per_minute=Decimal("0.0000"),
            trial_days=0,
            quota_period_anchor="calendar_month",
            extras_json={},
            published_at=datetime(2026, 5, 1, tzinfo=UTC),
        )

    async def get_by_slug(self, slug: str) -> Plan | None:
        return self.plan if slug in {"free", "enterprise"} else None

    async def get_published_version(self, plan_id: UUID) -> PlanVersion | None:
        return self.version if plan_id == self.plan.id else None


class _Session:
    def __init__(self, *, tenants: dict[UUID, Tenant], workspaces: dict[UUID, Workspace]) -> None:
        self.tenants = tenants
        self.workspaces = workspaces

    async def get(self, model: type[Any], identifier: UUID) -> Any | None:
        if model is Tenant:
            return self.tenants.get(identifier)
        if model is Workspace:
            return self.workspaces.get(identifier)
        return None


def _tenant(tenant_id: UUID, kind: str) -> Tenant:
    return Tenant(
        id=tenant_id,
        slug=f"{kind}-{tenant_id.hex[:8]}",
        kind=kind,
        subdomain=f"{kind}-{tenant_id.hex[:8]}",
        display_name=f"{kind.title()} Tenant",
        region="eu-west",
    )


def _workspace(workspace_id: UUID, tenant_id: UUID) -> Workspace:
    return Workspace(id=workspace_id, name="Workspace", owner_id=uuid4(), tenant_id=tenant_id)


def _service(
    subscription: Subscription | None,
    *,
    tenants: dict[UUID, Tenant] | None = None,
    workspaces: dict[UUID, Workspace] | None = None,
) -> SubscriptionService:
    return SubscriptionService(
        session=_Session(tenants=tenants or {}, workspaces=workspaces or {}),  # type: ignore[arg-type]
        subscriptions=_Subscriptions(subscription),  # type: ignore[arg-type]
        plans=_Plans(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_documented_subscription_transitions_succeed() -> None:
    subscription = _subscription("active")
    service = _service(subscription)

    scheduled = await service.downgrade_at_period_end(subscription.id, "free")
    assert scheduled.status == "cancellation_pending"
    assert scheduled.cancel_at_period_end is True

    restored = await service.cancel_scheduled_downgrade(subscription.id)
    assert restored.status == "active"
    assert restored.cancel_at_period_end is False

    suspended = await service.suspend(subscription.id, "manual review")
    assert suspended.status == "suspended"

    reactivated = await service.reactivate(subscription.id)
    assert reactivated.status == "active"

    subscription.status = "past_due"
    canceled = await service.cancel(subscription.id)
    assert canceled.status == "canceled"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "method_name"),
    [
        ("active", "cancel_scheduled_downgrade"),
        ("active", "reactivate"),
        ("canceled", "suspend"),
        ("canceled", "downgrade_at_period_end"),
    ],
)
async def test_undocumented_subscription_transitions_raise_typed_error(
    status: str,
    method_name: str,
) -> None:
    subscription = _subscription(status)
    service = _service(subscription)
    method = getattr(service, method_name)
    if method_name == "suspend":
        call = method(subscription.id, "manual review")
    elif method_name == "downgrade_at_period_end":
        call = method(subscription.id, "free")
    else:
        call = method(subscription.id)

    with pytest.raises(ConcurrentLifecycleActionError):
        await call


@pytest.mark.asyncio
async def test_scope_type_is_validated_against_tenant_kind() -> None:
    default_tenant_id = uuid4()
    enterprise_tenant_id = uuid4()
    enterprise_workspace_id = uuid4()
    service = _service(
        None,
        tenants={
            default_tenant_id: _tenant(default_tenant_id, "default"),
            enterprise_tenant_id: _tenant(enterprise_tenant_id, "enterprise"),
        },
        workspaces={
            enterprise_workspace_id: _workspace(enterprise_workspace_id, enterprise_tenant_id),
        },
    )

    with pytest.raises(SubscriptionScopeError):
        await service.provision_for_enterprise_tenant(default_tenant_id)

    with pytest.raises(SubscriptionScopeError):
        await service.provision_for_default_workspace(enterprise_workspace_id)
