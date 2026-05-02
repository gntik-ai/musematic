from __future__ import annotations

from platform.billing.exceptions import SubscriptionScopeError
from platform.billing.plans.repository import PlansRepository
from platform.billing.subscriptions.repository import SubscriptionsRepository
from platform.billing.subscriptions.service import SubscriptionService
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_subscription_scope_constraint_service_and_database_layers(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        default_tenant_id = await _default_tenant_id(session)
        enterprise_tenant_id = uuid4()
        default_workspace_id = uuid4()
        enterprise_workspace_id = uuid4()

        await _insert_enterprise_tenant(session, enterprise_tenant_id)
        await _insert_workspace_fixture(session, default_tenant_id, default_workspace_id)
        await _insert_workspace_fixture(session, enterprise_tenant_id, enterprise_workspace_id)

        service = SubscriptionService(
            session=session,
            subscriptions=SubscriptionsRepository(session),
            plans=PlansRepository(session),
        )

        await _set_tenant(session, default_tenant_id)
        default_subscription = await service.provision_for_default_workspace(
            default_workspace_id
        )
        assert default_subscription.scope_type == "workspace"
        assert default_subscription.scope_id == default_workspace_id

        await _set_tenant(session, enterprise_tenant_id)
        enterprise_subscription = await service.provision_for_enterprise_tenant(
            enterprise_tenant_id
        )
        assert enterprise_subscription.scope_type == "tenant"
        assert enterprise_subscription.scope_id == enterprise_tenant_id

        with pytest.raises(SubscriptionScopeError):
            await service.provision_for_enterprise_tenant(default_tenant_id)

        with pytest.raises(SubscriptionScopeError):
            await service.provision_for_default_workspace(enterprise_workspace_id)

        await _set_tenant(session, default_tenant_id)
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await _insert_subscription(
                    session,
                    tenant_id=default_tenant_id,
                    scope_type="tenant",
                    scope_id=default_tenant_id,
                    plan_slug="free",
                )

        await _set_tenant(session, enterprise_tenant_id)
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await _insert_subscription(
                    session,
                    tenant_id=enterprise_tenant_id,
                    scope_type="workspace",
                    scope_id=enterprise_workspace_id,
                    plan_slug="enterprise",
                )

        await session.rollback()


async def _set_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def _default_tenant_id(session: AsyncSession) -> UUID:
    tenant_id = await session.scalar(text("SELECT id FROM tenants WHERE kind = 'default' LIMIT 1"))
    assert isinstance(tenant_id, UUID)
    return tenant_id


async def _insert_enterprise_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    await session.execute(
        text(
            """
            INSERT INTO tenants (
                id,
                slug,
                kind,
                subdomain,
                display_name,
                region,
                data_isolation_mode,
                status
            )
            VALUES (
                :tenant_id,
                :slug,
                'enterprise',
                :slug,
                'Enterprise Scope Test',
                'eu-west',
                'pool',
                'active'
            )
            """
        ),
        {"tenant_id": str(tenant_id), "slug": f"ent-{tenant_id.hex[:8]}"},
    )


async def _insert_workspace_fixture(
    session: AsyncSession,
    tenant_id: UUID,
    workspace_id: UUID,
) -> None:
    await _set_tenant(session, tenant_id)
    owner_id = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO users (id, email, tenant_id, status)
            VALUES (:owner_id, :email, :tenant_id, 'active')
            """
        ),
        {
            "owner_id": str(owner_id),
            "email": f"scope-{owner_id.hex}@example.test",
            "tenant_id": str(tenant_id),
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO workspaces_workspaces (
                id,
                name,
                owner_id,
                tenant_id,
                status,
                is_default
            )
            VALUES (
                :workspace_id,
                :name,
                :owner_id,
                :tenant_id,
                'active',
                false
            )
            """
        ),
        {
            "workspace_id": str(workspace_id),
            "name": f"Scope {workspace_id.hex[:8]}",
            "owner_id": str(owner_id),
            "tenant_id": str(tenant_id),
        },
    )
    await session.flush()


async def _insert_subscription(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    scope_type: str,
    scope_id: UUID,
    plan_slug: str,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO subscriptions (
                tenant_id,
                scope_type,
                scope_id,
                plan_id,
                plan_version,
                status,
                current_period_start,
                current_period_end
            )
            SELECT
                :tenant_id,
                :scope_type,
                :scope_id,
                p.id,
                1,
                'active',
                now(),
                now() + interval '30 days'
              FROM plans p
             WHERE p.slug = :plan_slug
            """
        ),
        {
            "tenant_id": str(tenant_id),
            "scope_type": scope_type,
            "scope_id": str(scope_id),
            "plan_slug": plan_slug,
        },
    )
