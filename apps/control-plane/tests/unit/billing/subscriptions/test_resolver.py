from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.billing.exceptions import NoActiveSubscriptionError
from platform.billing.subscriptions.models import Subscription
from platform.billing.subscriptions.resolver import SubscriptionResolver
from platform.tenants.models import Tenant
from platform.workspaces.models import Workspace
from typing import Any
from uuid import UUID, uuid4

import pytest


class _Result:
    def __init__(self, value: Subscription | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Subscription | None:
        return self.value


class _Session:
    def __init__(
        self,
        *,
        workspaces: dict[UUID, Workspace],
        tenants: dict[UUID, Tenant],
        subscriptions: dict[tuple[str, UUID], Subscription],
    ) -> None:
        self.workspaces = workspaces
        self.tenants = tenants
        self.subscriptions = subscriptions

    async def get(self, model: type[Any], identifier: UUID) -> Any | None:
        if model is Workspace:
            return self.workspaces.get(identifier)
        if model is Tenant:
            return self.tenants.get(identifier)
        return None

    async def execute(self, statement: Any) -> _Result:
        params = statement.compile().params
        scope_type = _param_with_prefix(params, "scope_type")
        scope_id = _param_with_prefix(params, "scope_id")
        return _Result(self.subscriptions.get((scope_type, scope_id)))


def _param_with_prefix(params: dict[str, Any], prefix: str) -> Any:
    for key, value in params.items():
        if key.startswith(prefix):
            return value
    raise AssertionError(f"missing SQL parameter prefix: {prefix}")


def _tenant(tenant_id: UUID, *, kind: str) -> Tenant:
    return Tenant(
        id=tenant_id,
        slug=f"{kind}-{tenant_id.hex[:8]}",
        kind=kind,
        subdomain=f"{kind}-{tenant_id.hex[:8]}",
        display_name=f"{kind.title()} Tenant",
        region="eu-west",
    )


def _workspace(workspace_id: UUID, tenant_id: UUID) -> Workspace:
    return Workspace(
        id=workspace_id,
        name="Workspace",
        owner_id=uuid4(),
        tenant_id=tenant_id,
    )


def _subscription(tenant_id: UUID, *, scope_type: str, scope_id: UUID) -> Subscription:
    now = datetime(2026, 5, 1, tzinfo=UTC)
    return Subscription(
        id=uuid4(),
        tenant_id=tenant_id,
        scope_type=scope_type,
        scope_id=scope_id,
        plan_id=uuid4(),
        plan_version=1,
        status="active",
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )


@pytest.mark.asyncio
async def test_default_tenant_workspace_resolves_workspace_subscription() -> None:
    tenant_id = uuid4()
    workspace_id = uuid4()
    subscription = _subscription(tenant_id, scope_type="workspace", scope_id=workspace_id)
    resolver = SubscriptionResolver(
        _Session(
            workspaces={workspace_id: _workspace(workspace_id, tenant_id)},
            tenants={tenant_id: _tenant(tenant_id, kind="default")},
            subscriptions={("workspace", workspace_id): subscription},
        )  # type: ignore[arg-type]
    )

    assert await resolver.resolve_active_subscription(workspace_id) is subscription


@pytest.mark.asyncio
async def test_enterprise_workspace_resolves_tenant_subscription() -> None:
    tenant_id = uuid4()
    workspace_id = uuid4()
    subscription = _subscription(tenant_id, scope_type="tenant", scope_id=tenant_id)
    resolver = SubscriptionResolver(
        _Session(
            workspaces={workspace_id: _workspace(workspace_id, tenant_id)},
            tenants={tenant_id: _tenant(tenant_id, kind="enterprise")},
            subscriptions={("tenant", tenant_id): subscription},
        )  # type: ignore[arg-type]
    )

    assert await resolver.resolve_active_subscription(workspace_id) is subscription


@pytest.mark.asyncio
async def test_resolver_raises_when_no_active_subscription_exists() -> None:
    tenant_id = uuid4()
    workspace_id = uuid4()
    resolver = SubscriptionResolver(
        _Session(
            workspaces={workspace_id: _workspace(workspace_id, tenant_id)},
            tenants={tenant_id: _tenant(tenant_id, kind="default")},
            subscriptions={},
        )  # type: ignore[arg-type]
    )

    with pytest.raises(NoActiveSubscriptionError):
        await resolver.resolve_active_subscription(workspace_id)
