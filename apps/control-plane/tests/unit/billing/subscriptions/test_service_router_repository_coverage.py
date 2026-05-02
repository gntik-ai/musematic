from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.billing.exceptions import (
    ConcurrentLifecycleActionError,
    DowngradeAlreadyScheduledError,
    PlanNotFoundError,
    SubscriptionNotFoundError,
    SubscriptionScopeError,
    UpgradeFailedError,
)
from platform.billing.plans.models import Plan, PlanVersion
from platform.billing.quotas.models import OverageAuthorization
from platform.billing.subscriptions import admin_router as subscription_admin_router
from platform.billing.subscriptions import router as billing_router
from platform.billing.subscriptions.admin_router import _subscription_row
from platform.billing.subscriptions.models import Subscription
from platform.billing.subscriptions.repository import SubscriptionsRepository
from platform.billing.subscriptions.resolver import SubscriptionResolver
from platform.billing.subscriptions.schemas import (
    SubscriptionDowngrade,
    SubscriptionMigrate,
    SubscriptionUpgrade,
)
from platform.billing.subscriptions.service import SubscriptionService, _add_month, _period_bounds
from platform.common.config import PlatformSettings
from platform.tenants.models import Tenant
from platform.workspaces.models import Workspace
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from tests.unit.billing.quotas.test_runtime_coverage import (
    _Result,
    _Session,
    _SessionContext,
    _authorization,
    _plan,
    _subscription,
    _version,
)

NOW = datetime(2026, 5, 1, tzinfo=UTC)


class _Row(dict[str, Any]):
    def __getattr__(self, name: str) -> Any:
        return self[name]


class _Producer:
    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []

    async def publish(self, *args: Any) -> None:
        self.events.append(args)


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []

    async def append(self, *args: Any, **kwargs: Any) -> None:
        self.events.append((*args, kwargs))


class _Quota:
    def __init__(self) -> None:
        self.invalidated: list[UUID] = []

    async def invalidate_workspace(self, workspace_id: UUID) -> None:
        self.invalidated.append(workspace_id)


class _ProviderSubscription:
    provider_subscription_id = "sub_123"
    current_period_start = NOW
    current_period_end = NOW + timedelta(days=30)


class _PaymentProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def create_customer(self, *args: Any) -> str:
        self.calls.append(("create_customer", args))
        return "cus_123"

    async def attach_payment_method(self, *args: Any) -> str:
        self.calls.append(("attach_payment_method", args))
        return "pm_card_visa"

    async def update_subscription(self, *args: Any) -> _ProviderSubscription:
        self.calls.append(("update_subscription", args))
        return _ProviderSubscription()

    async def cancel_subscription(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("cancel_subscription", (*args, kwargs)))

    async def preview_proration(self, *args: Any) -> SimpleNamespace:
        self.calls.append(("preview_proration", args))
        return SimpleNamespace(
            prorated_charge_eur=Decimal("1.00"),
            prorated_credit_eur=Decimal("0.25"),
            next_full_invoice_eur=Decimal("19.00"),
            effective_at=NOW,
        )


class _Store:
    def __init__(self, subscription: Subscription | None = None) -> None:
        self.subscription = subscription
        self.created: list[Subscription] = []

    async def get_by_id(self, subscription_id: UUID) -> Subscription | None:
        if self.subscription is not None and self.subscription.id == subscription_id:
            return self.subscription
        return None

    async def get_by_scope(self, scope_type: str, scope_id: UUID) -> Subscription | None:
        if (
            self.subscription is not None
            and self.subscription.scope_type == scope_type
            and self.subscription.scope_id == scope_id
        ):
            return self.subscription
        return None

    async def create(self, **kwargs: Any) -> Subscription:
        subscription = Subscription(
            id=uuid4(),
            started_at=NOW,
            created_at=NOW,
            updated_at=NOW,
            **kwargs,
        )
        self.subscription = subscription
        self.created.append(subscription)
        return subscription

    async def update_plan_pinning(self, subscription_id: UUID, **kwargs: Any) -> Subscription | None:
        subscription = await self.get_by_id(subscription_id)
        if subscription is None:
            return None
        for key, value in kwargs.items():
            if value is not None:
                setattr(subscription, key, value)
        return subscription

    async def update_status(self, subscription_id: UUID, status: str) -> Subscription | None:
        subscription = await self.get_by_id(subscription_id)
        if subscription is None:
            return None
        subscription.status = status
        if status == "canceled":
            subscription.cancel_at_period_end = False
        return subscription

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


class _Plans:
    def __init__(self, free: Plan, pro: Plan, enterprise: Plan) -> None:
        self.by_slug = {free.slug: free, pro.slug: pro, enterprise.slug: enterprise}
        self.versions = {
            free.id: _version(free, executions_per_month=50),
            pro.id: _version(pro, executions_per_month=500),
            enterprise.id: _version(
                enterprise,
                executions_per_month=0,
                minutes_per_month=0,
                max_workspaces=0,
                max_agents_per_workspace=0,
                max_users_per_workspace=0,
            ),
        }
        self.versions[free.id].trial_days = 7

    async def get_by_slug(self, slug: str) -> Plan | None:
        return self.by_slug.get(slug)

    async def get_published_version(self, plan_id: UUID) -> PlanVersion | None:
        return self.versions.get(plan_id)


class _ServiceSession(_Session):
    def __init__(
        self,
        *,
        tenants: dict[UUID, Tenant],
        workspaces: dict[UUID, Workspace],
        plans: dict[UUID, Plan],
    ) -> None:
        super().__init__()
        self.tenants = tenants
        self.workspaces = workspaces
        self.plans = plans

    async def get(self, model: type[Any], identifier: UUID) -> Any | None:
        if model is Tenant:
            return self.tenants.get(identifier)
        if model is Workspace:
            return self.workspaces.get(identifier)
        if model is Plan:
            return self.plans.get(identifier)
        return None


class _MappingResult:
    def __init__(self, rows: list[_Row]) -> None:
        self.rows = rows

    def mappings(self) -> _MappingResult:
        return self

    def all(self) -> list[_Row]:
        return self.rows

    def one_or_none(self) -> _Row | None:
        return self.rows[0] if self.rows else None


class _IterableResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def __iter__(self) -> object:
        return iter(self.rows)


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
    *,
    session: _ServiceSession,
    store: _Store,
    plans: _Plans,
    payment_provider: object | None = None,
    audit_chain: object | None = None,
    producer: object | None = None,
    quota_enforcer: object | None = None,
) -> SubscriptionService:
    return SubscriptionService(
        session=session,  # type: ignore[arg-type]
        subscriptions=store,  # type: ignore[arg-type]
        plans=plans,  # type: ignore[arg-type]
        payment_provider=payment_provider,  # type: ignore[arg-type]
        audit_chain=audit_chain,  # type: ignore[arg-type]
        producer=producer,  # type: ignore[arg-type]
        quota_enforcer=quota_enforcer,
    )


@pytest.mark.asyncio
async def test_subscription_service_provision_upgrade_cancel_and_migrate_paths() -> None:
    default_tenant_id = uuid4()
    enterprise_tenant_id = uuid4()
    workspace_id = uuid4()
    free = _plan(slug="free", tier="free", allowed_model_tier="cheap_only")
    pro = _plan(slug="pro", tier="pro", allowed_model_tier="standard")
    enterprise = _plan(slug="enterprise", tier="enterprise", allowed_model_tier="all")
    plans = _Plans(free, pro, enterprise)
    store = _Store()
    producer = _Producer()
    audit = _Audit()
    quota = _Quota()
    provider = _PaymentProvider()
    session = _ServiceSession(
        tenants={
            default_tenant_id: _tenant(default_tenant_id, "default"),
            enterprise_tenant_id: _tenant(enterprise_tenant_id, "enterprise"),
        },
        workspaces={workspace_id: _workspace(workspace_id, default_tenant_id)},
        plans={free.id: free, pro.id: pro, enterprise.id: enterprise},
    )
    service = SubscriptionService(
        session=session,  # type: ignore[arg-type]
        subscriptions=store,  # type: ignore[arg-type]
        plans=plans,  # type: ignore[arg-type]
        payment_provider=provider,  # type: ignore[arg-type]
        audit_chain=audit,  # type: ignore[arg-type]
        producer=producer,  # type: ignore[arg-type]
        quota_enforcer=quota,
    )

    created = await service.provision_for_default_workspace(
        workspace_id,
        created_by_user_id=uuid4(),
    )
    created.status = "active"
    upgraded = await service.upgrade(workspace_id, "pro", "tok_visa", actor_id=uuid4())
    migrated = await service.migrate_version(upgraded.id, pro.id, 2)
    canceled = await service.cancel(migrated.id)

    enterprise_service = SubscriptionService(
        session=session,  # type: ignore[arg-type]
        subscriptions=_Store(),  # type: ignore[arg-type]
        plans=plans,  # type: ignore[arg-type]
        producer=producer,  # type: ignore[arg-type]
    )
    enterprise_subscription = await enterprise_service.provision_for_enterprise_tenant(
        enterprise_tenant_id
    )

    assert store.created[0].scope_id == workspace_id
    assert upgraded.plan_id == pro.id
    assert migrated.plan_version == 2
    assert canceled.status == "canceled"
    assert enterprise_subscription.scope_type == "tenant"
    assert quota.invalidated == [workspace_id]
    assert {event[2] for event in producer.events} >= {
        "billing.subscription.created",
        "billing.subscription.upgraded",
        "billing.subscription.canceled",
    }
    assert audit.events
    assert [call[0] for call in provider.calls] >= [
        "create_customer",
        "attach_payment_method",
        "update_subscription",
        "cancel_subscription",
    ]


@pytest.mark.asyncio
async def test_subscription_service_guard_error_and_providerless_paths() -> None:
    default_tenant_id = uuid4()
    enterprise_tenant_id = uuid4()
    workspace_id = uuid4()
    missing_workspace_id = uuid4()
    free = _plan(slug="free", tier="free", allowed_model_tier="cheap_only")
    pro = _plan(slug="pro", tier="pro", allowed_model_tier="standard")
    enterprise = _plan(slug="enterprise", tier="enterprise", allowed_model_tier="all")
    inactive = _plan(slug="inactive", tier="enterprise", allowed_model_tier="all")
    inactive.is_active = False
    plans = _Plans(free, pro, enterprise)
    plans.by_slug[inactive.slug] = inactive
    plans.versions[inactive.id] = _version(inactive)
    session = _ServiceSession(
        tenants={
            default_tenant_id: _tenant(default_tenant_id, "default"),
            enterprise_tenant_id: _tenant(enterprise_tenant_id, "enterprise"),
        },
        workspaces={workspace_id: _workspace(workspace_id, default_tenant_id)},
        plans={free.id: free, pro.id: pro, enterprise.id: enterprise, inactive.id: inactive},
    )
    active = _subscription(free)
    active.scope_id = workspace_id
    active.tenant_id = default_tenant_id
    store = _Store(active)
    service = _service(session=session, store=store, plans=plans)

    assert await service.provision_for_default_workspace(workspace_id) is active
    enterprise_subscription = await service.provision_for_enterprise_tenant(enterprise_tenant_id)
    assert await service.provision_for_enterprise_tenant(enterprise_tenant_id) is enterprise_subscription
    with pytest.raises(SubscriptionNotFoundError):
        await service.provision_for_default_workspace(missing_workspace_id)
    with pytest.raises(SubscriptionScopeError):
        await service.provision_for_enterprise_tenant(default_tenant_id)

    store.subscription = None
    with pytest.raises(SubscriptionNotFoundError):
        await service.upgrade(missing_workspace_id, "pro", None)
    with pytest.raises(SubscriptionNotFoundError):
        await service.upgrade(workspace_id, "pro", None)
    store.subscription = active
    with pytest.raises(PlanNotFoundError):
        await service.upgrade(workspace_id, "missing", None)
    with pytest.raises(PlanNotFoundError):
        await service.upgrade(workspace_id, "inactive", None)
    session.plans.pop(active.plan_id)
    with pytest.raises(PlanNotFoundError):
        await service.upgrade(workspace_id, "pro", None)
    session.plans[active.plan_id] = free
    with pytest.raises(UpgradeFailedError):
        await service.upgrade(workspace_id, "free", None)
    plans.versions.pop(pro.id)
    with pytest.raises(PlanNotFoundError):
        await service.upgrade(workspace_id, "pro", None)
    plans.versions[pro.id] = _version(pro)

    providerless = await service.upgrade(workspace_id, "pro", None)
    assert providerless.plan_id == pro.id

    store.subscription = None
    with pytest.raises(SubscriptionNotFoundError):
        await service.downgrade_at_period_end(workspace_id, "free")
    store.subscription = active
    active.cancel_at_period_end = True
    with pytest.raises(DowngradeAlreadyScheduledError):
        await service.downgrade_at_period_end(workspace_id, "free")
    active.cancel_at_period_end = False
    active.status = "suspended"
    with pytest.raises(ConcurrentLifecycleActionError):
        await service.downgrade_at_period_end(workspace_id, "free")
    active.status = "active"
    with pytest.raises(PlanNotFoundError):
        await service.downgrade_at_period_end(workspace_id, "missing")
    session.plans.pop(active.plan_id)
    with pytest.raises(PlanNotFoundError):
        await service.downgrade_at_period_end(workspace_id, "free")
    session.plans[active.plan_id] = pro
    with pytest.raises(ConcurrentLifecycleActionError):
        await service.downgrade_at_period_end(workspace_id, "enterprise")

    active.status = "active"
    with pytest.raises(ConcurrentLifecycleActionError):
        await service.cancel_scheduled_downgrade(workspace_id)
    provider = _PaymentProvider()
    service_with_provider = _service(
        session=session,
        store=store,
        plans=plans,
        payment_provider=provider,
    )
    assert (
        await service_with_provider.downgrade_at_period_end(workspace_id, "free")
    ).cancel_at_period_end
    store.subscription = None
    with pytest.raises(SubscriptionNotFoundError):
        await service.cancel_scheduled_downgrade(workspace_id)
    store.subscription = active
    session.plans.pop(active.plan_id)
    assert (await service_with_provider.cancel_scheduled_downgrade(workspace_id)).status == "active"
    assert provider.calls[-1][0] == "update_subscription"
    session.plans[active.plan_id] = pro

    store.subscription = None
    with pytest.raises(SubscriptionNotFoundError):
        await service.suspend(active.id, "billing")
    store.subscription = active
    active.status = "canceled"
    with pytest.raises(ConcurrentLifecycleActionError):
        await service.suspend(active.id, "billing")
    active.status = "active"
    assert (await service.suspend(active.id, "billing")).status == "suspended"

    store.subscription = None
    with pytest.raises(SubscriptionNotFoundError):
        await service.reactivate(active.id)
    store.subscription = active
    active.status = "active"
    with pytest.raises(ConcurrentLifecycleActionError):
        await service.reactivate(active.id)
    active.status = "past_due"
    assert (await service.reactivate(active.id)).status == "active"

    store.subscription = None
    with pytest.raises(SubscriptionNotFoundError):
        await service.cancel(active.id)
    store.subscription = active
    active.status = "canceled"
    with pytest.raises(ConcurrentLifecycleActionError):
        await service.cancel(active.id)

    store.subscription = None
    with pytest.raises(SubscriptionNotFoundError):
        await service.migrate_version(active.id, pro.id, 3)
    store.subscription = active
    active.status = "suspended"
    with pytest.raises(ConcurrentLifecycleActionError):
        await service.migrate_version(active.id, pro.id, 3)

    with pytest.raises(PlanNotFoundError):
        await service._provision(
            tenant_id=default_tenant_id,
            scope_type="workspace",
            scope_id=workspace_id,
            plan_slug="missing",
            created_by_user_id=None,
        )
    plans.by_slug["noversion"] = _plan(slug="noversion", tier="pro")
    with pytest.raises(PlanNotFoundError):
        await service._provision(
            tenant_id=default_tenant_id,
            scope_type="workspace",
            scope_id=workspace_id,
            plan_slug="noversion",
            created_by_user_id=None,
        )

    assert await service._workspace_or_subscription(active.id) is active
    rolling_start, rolling_end = _period_bounds(NOW, "rolling")
    assert rolling_end - rolling_start == timedelta(days=30)
    assert _add_month(datetime(2026, 12, 1, tzinfo=UTC)).month == 1


@pytest.mark.asyncio
async def test_subscriptions_repository_methods_cover_update_paths() -> None:
    plan = _plan()
    subscription = _subscription(plan)
    session = _Session(
        execute_results=[
            _Result(scalar=subscription),
            _Result(rows=[subscription]),
            _Result(rows=[subscription]),
            _Result(scalar=subscription),
            _Result(scalar=subscription),
            _Result(scalar=subscription),
            _Result(rows=[subscription]),
            _Result(rows=[subscription.id]),
        ],
        get_values={(Subscription, subscription.id): subscription},
    )
    repository = SubscriptionsRepository(session)  # type: ignore[arg-type]

    assert await repository.get_by_id(subscription.id) is subscription
    assert await repository.get_by_scope("workspace", subscription.scope_id) is subscription
    assert await repository.list_for_tenant(subscription.tenant_id) == [subscription]
    assert await repository.list_all(limit=1) == [subscription]
    created = await repository.create(
        tenant_id=subscription.tenant_id,
        scope_type="workspace",
        scope_id=subscription.scope_id,
        plan_id=subscription.plan_id,
        plan_version=subscription.plan_version,
        status="active",
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
    )
    assert created in session.added
    assert await repository.update_status(subscription.id, "suspended") is subscription
    assert (
        await repository.update_plan_pinning(
            subscription.id,
            plan_id=subscription.plan_id,
            plan_version=2,
            current_period_start=NOW,
            current_period_end=NOW + timedelta(days=30),
            payment_method_id=uuid4(),
            status="active",
            stripe_customer_id="cus",
            stripe_subscription_id="sub",
        )
        is subscription
    )
    assert await repository.set_cancel_at_period_end(subscription.id, True) is subscription
    assert await repository.list_due_for_period_rollover(NOW) == [subscription]
    assert await repository.advance_period(
        subscription,
        new_period_start=NOW,
        new_period_end=NOW + timedelta(days=30),
        status="canceled",
    ) is subscription
    assert await repository.count_by_plan_version(subscription.plan_id, 2) == 1


@pytest.mark.asyncio
async def test_subscription_resolver_missing_workspace_and_tenant_paths() -> None:
    workspace_id = uuid4()
    tenant_id = uuid4()
    with pytest.raises(Exception):
        await SubscriptionResolver(_Session()).resolve_active_subscription(workspace_id)  # type: ignore[arg-type]
    with pytest.raises(Exception):
        await SubscriptionResolver(
            _ServiceSession(
                tenants={},
                workspaces={workspace_id: _workspace(workspace_id, tenant_id)},
                plans={},
            )
        ).resolve_active_subscription(workspace_id)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_workspace_billing_router_helpers_and_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(slug="pro", tier="pro")
    version = _version(plan, minutes_per_month=10, overage_price_per_minute=Decimal("0.25"))
    subscription = _subscription(plan)
    authorization = _authorization(subscription, max_overage_eur=Decimal("3.00"))
    user_id = uuid4()
    session = _Session(scalar_results=["admin", 2, 4, 3, *(["admin"] * 8)])
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(clients={"kafka": _Producer()}, settings=object()))
    )

    class _UsageRepository:
        def __init__(self, session: object) -> None:
            del session

        async def get_current_usage(self, *args: object) -> dict[str, Decimal]:
            del args
            return {"executions": Decimal("7"), "minutes": Decimal("5")}

        async def get_period_history(self, *args: object, **kwargs: object) -> list[Any]:
            del args, kwargs
            return [
                SimpleNamespace(
                    metric="minutes",
                    period_start=NOW,
                    period_end=NOW + timedelta(days=30),
                    quantity=Decimal("5"),
                    is_overage=False,
                )
            ]

    class _OverageService:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        async def authorize(self, *args: object) -> OverageAuthorization:
            del args
            return authorization

        async def revoke(self, *args: object) -> OverageAuthorization:
            del args
            authorization.revoked_at = NOW
            return authorization

    class _SubscriptionService:
        async def upgrade(self, *args: object, **kwargs: object) -> Subscription:
            del args, kwargs
            subscription.plan_version = 2
            return subscription

        async def downgrade_at_period_end(self, *args: object) -> Subscription:
            del args
            subscription.status = "cancellation_pending"
            subscription.cancel_at_period_end = True
            return subscription

        async def cancel_scheduled_downgrade(self, *args: object) -> Subscription:
            del args
            subscription.status = "active"
            subscription.cancel_at_period_end = False
            return subscription

        async def cancel(self, *args: object) -> Subscription:
            del args
            subscription.status = "canceled"
            return subscription

    async def _context(session_arg: object, workspace_id: UUID) -> tuple[Subscription, Plan, PlanVersion]:
        del session_arg
        assert workspace_id == subscription.scope_id
        return subscription, plan, version

    monkeypatch.setattr(billing_router, "UsageRepository", _UsageRepository)
    monkeypatch.setattr(billing_router, "OverageService", _OverageService)
    monkeypatch.setattr(billing_router, "_subscription_context", _context)
    monkeypatch.setattr(
        billing_router,
        "_current_overage_state",
        lambda *args: _async_value(
            {
                "billing_period_start": NOW.isoformat(),
                "billing_period_end": (NOW + timedelta(days=30)).isoformat(),
                "is_authorized": True,
            }
        ),
    )
    monkeypatch.setattr(
        billing_router,
        "_current_authorization",
        lambda *args: _async_value(authorization),
    )
    monkeypatch.setattr(
        billing_router,
        "_subscription_service",
        lambda *args, **kwargs: _SubscriptionService(),
    )
    monkeypatch.setattr(
        billing_router,
        "_preview_proration",
        lambda *args: _async_value(
            {
                "prorated_charge_eur": Decimal("1.00"),
                "prorated_credit_eur": Decimal("0.25"),
                "next_full_invoice_eur": Decimal("19.00"),
                "effective_at": NOW,
            }
        ),
    )

    summary = await billing_router.get_billing_summary(
        subscription.scope_id,
        {"sub": str(user_id)},
        session,  # type: ignore[arg-type]
    )
    overage = await billing_router.get_overage_authorization(
        subscription.scope_id,
        {"sub": str(user_id)},
        session,  # type: ignore[arg-type]
    )
    authorized = await billing_router.authorize_overage(
        subscription.scope_id,
        SimpleNamespace(max_overage_eur=Decimal("3.00")),
        request,  # type: ignore[arg-type]
        {"sub": str(user_id)},
        session,  # type: ignore[arg-type]
    )
    revoked = await billing_router.revoke_overage(
        subscription.scope_id,
        request,  # type: ignore[arg-type]
        {"sub": str(user_id)},
        session,  # type: ignore[arg-type]
    )
    history = await billing_router.get_usage_history(
        subscription.scope_id,
        6,
        {"sub": str(user_id)},
        session,  # type: ignore[arg-type]
    )
    upgrade = await billing_router.upgrade_subscription(
        subscription.scope_id,
        SubscriptionUpgrade(target_plan_slug="pro", payment_method_token="tok"),
        request,  # type: ignore[arg-type]
        {"sub": str(user_id)},
        session,  # type: ignore[arg-type]
    )
    downgrade = await billing_router.downgrade_subscription(
        subscription.scope_id,
        SubscriptionDowngrade(target_plan_slug="free"),
        request,  # type: ignore[arg-type]
        {"sub": str(user_id)},
        session,  # type: ignore[arg-type]
    )
    cancelled = await billing_router.cancel_downgrade(
        subscription.scope_id,
        request,  # type: ignore[arg-type]
        {"sub": str(user_id)},
        session,  # type: ignore[arg-type]
    )
    canceled = await billing_router.cancel_subscription(
        subscription.scope_id,
        request,  # type: ignore[arg-type]
        {"sub": str(user_id)},
        session,  # type: ignore[arg-type]
    )

    assert summary["subscription"]["plan_slug"] == "pro"
    assert overage["is_authorized"] is True
    assert authorized["is_authorized"] is True
    assert revoked.status_code == 204
    assert history["items"][0]["metric"] == "minutes"
    assert upgrade["preview"]["prorated_charge_eur"] == "1.00"
    assert downgrade["cancel_at_period_end"] is True
    assert cancelled["cancel_at_period_end"] is False
    assert canceled["status"] == "canceled"
    assert billing_router._available_actions("free", "active") == ["upgrade_to_pro"]
    assert billing_router._available_actions("enterprise", "active") == []
    assert billing_router._authorization_response(authorization, is_authorized=False)[
        "max_overage_eur"
    ] == "3.00"
    assert billing_router._burn_rate(Decimal("5"), NOW - timedelta(days=5), NOW) > 0


@pytest.mark.asyncio
async def test_workspace_billing_router_internal_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _plan(slug="pro", tier="pro")
    version = _version(plan, minutes_per_month=10, overage_price_per_minute=Decimal("0.25"))
    subscription = _subscription(plan)
    user_id = uuid4()
    authorization = _authorization(subscription, max_overage_eur=Decimal("4.00"))

    with pytest.raises(Exception):
        await billing_router._require_workspace_member(_Session(scalar_results=[None]), uuid4(), user_id)  # type: ignore[arg-type]
    with pytest.raises(Exception):
        await billing_router._require_workspace_admin(_Session(scalar_results=["member"]), uuid4(), user_id)  # type: ignore[arg-type]

    class _Resolver:
        def __init__(self, session: object) -> None:
            del session

        async def resolve_active_subscription(self, workspace_id: UUID) -> Subscription:
            assert workspace_id == subscription.scope_id
            return subscription

    monkeypatch.setattr(billing_router, "SubscriptionResolver", _Resolver)
    session = _Session(execute_results=[_Result(rows=[(plan, version)]), _Result()])
    resolved = await billing_router._subscription_context(session, subscription.scope_id)  # type: ignore[arg-type]
    assert resolved == (subscription, plan, version)
    with pytest.raises(Exception):
        await billing_router._subscription_context(session, subscription.scope_id)  # type: ignore[arg-type]

    class _PlansRepository:
        def __init__(self, session_arg: object) -> None:
            del session_arg

        async def get_by_slug(self, slug: str) -> Plan | None:
            return plan if slug == "pro" else None

        async def get_published_version(self, plan_id: UUID) -> PlanVersion | None:
            assert plan_id == plan.id
            return version

    class _Provider:
        async def preview_proration(self, *args: object) -> SimpleNamespace:
            del args
            return SimpleNamespace(
                prorated_charge_eur=Decimal("1.25"),
                prorated_credit_eur=Decimal("0.50"),
                next_full_invoice_eur=Decimal("19.00"),
                effective_at=NOW,
            )

    monkeypatch.setattr(billing_router, "PlansRepository", _PlansRepository)
    preview = await billing_router._preview_proration(
        _Session(),  # type: ignore[arg-type]
        _Provider(),  # type: ignore[arg-type]
        subscription,
        "pro",
    )
    missing_preview = await billing_router._preview_proration(
        _Session(),  # type: ignore[arg-type]
        _Provider(),  # type: ignore[arg-type]
        subscription,
        "missing",
    )
    no_provider_preview = await billing_router._preview_proration(
        _Session(),  # type: ignore[arg-type]
        None,
        subscription,
        "pro",
    )

    overage_session = _Session(
        execute_results=[_Result(scalar=authorization)],
        get_values={(Subscription, subscription.id): subscription},
        scalar_results=[version, Decimal("2")],
    )
    overage = await billing_router._current_overage_state(
        overage_session,  # type: ignore[arg-type]
        subscription.scope_id,
        subscription,
    )

    class _Audit:
        pass

    class _Quota:
        pass

    monkeypatch.setattr(billing_router, "build_audit_chain_service", lambda *args: _Audit())
    monkeypatch.setattr(billing_router, "build_quota_enforcer", lambda **kwargs: _Quota())
    service = billing_router._subscription_service(
        _Session(),  # type: ignore[arg-type]
        SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    clients={"kafka": _Producer(), "redis": object()},
                    settings=PlatformSettings(),
                )
            )
        ),  # type: ignore[arg-type]
        payment_provider=_Provider(),  # type: ignore[arg-type]
    )

    assert preview["prorated_charge_eur"] == Decimal("1.25")
    assert missing_preview["next_full_invoice_eur"] == Decimal("0.00")
    assert no_provider_preview["prorated_charge_eur"] == Decimal("0.00")
    assert overage["current_overage_eur"] == "0.50"
    assert billing_router._available_actions("pro", "cancellation_pending") == [
        "cancel_downgrade"
    ]
    assert service.payment_provider is not None


@pytest.mark.asyncio
async def test_subscription_admin_router_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _plan(slug="pro", tier="pro")
    version = _version(plan)
    subscription = _subscription(plan)
    row = _Row(
        id=subscription.id,
        tenant_id=subscription.tenant_id,
        tenant_slug="tenant",
        scope_type=subscription.scope_type,
        scope_id=subscription.scope_id,
        plan_slug=plan.slug,
        plan_tier=plan.tier,
        plan_version=subscription.plan_version,
        status=subscription.status,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        cancel_at_period_end=False,
        created_at=NOW,
        stripe_customer_id="cus",
        stripe_subscription_id="sub",
    )
    usage_row = SimpleNamespace(
        metric="minutes",
        period_start=NOW,
        period_end=NOW + timedelta(days=30),
        quantity=Decimal("3.5"),
        is_overage=True,
    )
    session = _SessionContext(
        execute_results=[
            _MappingResult([row]),  # type: ignore[list-item]
            _IterableResult([usage_row]),  # type: ignore[list-item]
            _MappingResult([row]),  # type: ignore[list-item]
            _MappingResult([]),  # type: ignore[list-item]
        ],
        scalar_results=[version, None],
    )
    original_service = subscription_admin_router._service

    class _AdminSubscriptionsRepository:
        def __init__(self, session_arg: object) -> None:
            del session_arg

        async def get_by_id(self, subscription_id: UUID) -> Subscription | None:
            return subscription if subscription_id == subscription.id else None

    class _AdminPlansRepository:
        def __init__(self, session_arg: object) -> None:
            del session_arg

        async def get_by_slug(self, slug: str) -> Plan | None:
            return plan if slug == plan.slug else None

    class _AdminService:
        async def suspend(self, subscription_id: UUID, reason: str) -> Subscription:
            assert subscription_id == subscription.id
            assert reason == "billing"
            subscription.status = "suspended"
            return subscription

        async def reactivate(self, subscription_id: UUID) -> Subscription:
            assert subscription_id == subscription.id
            subscription.status = "active"
            return subscription

        async def migrate_version(
            self,
            subscription_id: UUID,
            plan_id: UUID,
            plan_version: int,
        ) -> Subscription:
            assert subscription_id == subscription.id
            assert plan_id == plan.id
            subscription.plan_version = plan_version
            return subscription

    monkeypatch.setattr(
        subscription_admin_router.database,
        "PlatformStaffAsyncSessionLocal",
        lambda: session,
    )
    monkeypatch.setattr(
        subscription_admin_router,
        "SubscriptionsRepository",
        _AdminSubscriptionsRepository,
    )
    monkeypatch.setattr(subscription_admin_router, "PlansRepository", _AdminPlansRepository)
    monkeypatch.setattr(subscription_admin_router, "_service", lambda *args: _AdminService())

    listed = await subscription_admin_router.list_subscriptions(
        SimpleNamespace(),
        status="active",
        plan_slug="pro",
        limit=2000,
    )
    usage = await subscription_admin_router.get_subscription_usage(subscription.id)
    detail = await subscription_admin_router.get_subscription(subscription.id)
    suspended = await subscription_admin_router.suspend_subscription(
        subscription.id,
        SimpleNamespace(),
        {"reason": "billing"},
    )
    reactivated = await subscription_admin_router.reactivate_subscription(
        subscription.id,
        SimpleNamespace(),
    )
    migrated = await subscription_admin_router.migrate_subscription_version(
        subscription.id,
        SubscriptionMigrate(plan_slug="pro", plan_version=2, reason="test"),
        SimpleNamespace(),
    )
    with pytest.raises(SubscriptionNotFoundError):
        await subscription_admin_router.get_subscription_usage(uuid4())
    with pytest.raises(SubscriptionNotFoundError):
        await subscription_admin_router.get_subscription(uuid4())
    with pytest.raises(PlanNotFoundError):
        await subscription_admin_router.migrate_subscription_version(
            subscription.id,
            SubscriptionMigrate(plan_slug="missing", plan_version=2, reason="test"),
            SimpleNamespace(),
        )
    with pytest.raises(Exception):
        await subscription_admin_router.migrate_subscription_version(
            subscription.id,
            SubscriptionMigrate(plan_slug="pro", plan_version=99, reason="test"),
            SimpleNamespace(),
        )
    built_service = original_service(
        _Session(),  # type: ignore[arg-type]
        SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(clients={}, settings=PlatformSettings())
            )
        ),  # type: ignore[arg-type]
    )

    assert listed["items"][0]["id"] == str(subscription.id)
    assert usage["items"][0]["quantity"] == "3.5"
    assert detail["stripe_customer_id"] == "cus"
    assert suspended["status"] == "suspended"
    assert reactivated["status"] == "active"
    assert migrated["plan_version"] == 2
    assert session.committed is True
    assert built_service.producer is None


def test_subscription_admin_row_serialization() -> None:
    row = _Row(
        id=uuid4(),
        tenant_id=uuid4(),
        tenant_slug="tenant",
        scope_type="workspace",
        scope_id=uuid4(),
        plan_slug="pro",
        plan_tier="pro",
        plan_version=1,
        status="active",
        current_period_start=NOW,
        current_period_end=NOW + timedelta(days=30),
        cancel_at_period_end=False,
        created_at=NOW,
        stripe_customer_id="cus",
        stripe_subscription_id="sub",
    )

    assert _subscription_row(row)["stripe_subscription_id"] == "sub"


async def _async_value(value: Any) -> Any:
    return value
