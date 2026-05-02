from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class QuotaWorkspaceFixture:
    tenant_id: UUID
    workspace_id: UUID
    owner_id: UUID
    subscription_id: UUID
    period_start: datetime
    period_end: datetime


async def set_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def default_tenant_id(session: AsyncSession) -> UUID:
    tenant_id = await session.scalar(text("SELECT id FROM tenants WHERE kind = 'default' LIMIT 1"))
    assert isinstance(tenant_id, UUID)
    return tenant_id


async def create_workspace_subscription(
    session: AsyncSession,
    *,
    plan_slug: str = "free",
    executions: int = 0,
    minutes: Decimal = Decimal("0"),
    member_count: int = 1,
    workspace_id: UUID | None = None,
    owner_id: UUID | None = None,
) -> QuotaWorkspaceFixture:
    tenant_id = await default_tenant_id(session)
    await set_tenant(session, tenant_id)
    owner_id = owner_id or uuid4()
    workspace_id = workspace_id or uuid4()
    subscription_id = uuid4()
    period_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start + timedelta(days=31)
    await session.execute(
        text(
            """
            INSERT INTO users (id, email, tenant_id, status)
            VALUES (:owner_id, :email, :tenant_id, 'active')
            """
        ),
        {
            "owner_id": str(owner_id),
            "email": f"quota-{owner_id.hex}@example.test",
            "tenant_id": str(tenant_id),
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO workspaces_workspaces (id, name, owner_id, tenant_id, status, is_default)
            VALUES (:workspace_id, :name, :owner_id, :tenant_id, 'active', false)
            """
        ),
        {
            "workspace_id": str(workspace_id),
            "name": f"Quota {workspace_id.hex[:8]}",
            "owner_id": str(owner_id),
            "tenant_id": str(tenant_id),
        },
    )
    for index in range(member_count):
        user_id = owner_id if index == 0 else uuid4()
        if index > 0:
            await session.execute(
                text(
                    """
                    INSERT INTO users (id, email, tenant_id, status)
                    VALUES (:user_id, :email, :tenant_id, 'active')
                    """
                ),
                {
                    "user_id": str(user_id),
                    "email": f"quota-member-{user_id.hex}@example.test",
                    "tenant_id": str(tenant_id),
                },
        )
        await session.execute(
            text(
                """
                INSERT INTO workspaces_memberships (workspace_id, user_id, tenant_id, role)
                VALUES (:workspace_id, :user_id, :tenant_id, 'member')
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "workspace_id": str(workspace_id),
                "user_id": str(user_id),
                "tenant_id": str(tenant_id),
            },
        )
    await session.execute(
        text(
            """
            INSERT INTO subscriptions (
                id,
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
                :subscription_id,
                :tenant_id,
                'workspace',
                :workspace_id,
                p.id,
                1,
                'active',
                :period_start,
                :period_end
              FROM plans p
             WHERE p.slug = :plan_slug
            """
        ),
        {
            "subscription_id": str(subscription_id),
            "tenant_id": str(tenant_id),
            "workspace_id": str(workspace_id),
            "period_start": period_start,
            "period_end": period_end,
            "plan_slug": plan_slug,
        },
    )
    if executions:
        await _insert_usage(
            session,
            tenant_id,
            workspace_id,
            subscription_id,
            period_start,
            period_end,
            "executions",
            Decimal(executions),
        )
    if minutes:
        await _insert_usage(
            session,
            tenant_id,
            workspace_id,
            subscription_id,
            period_start,
            period_end,
            "minutes",
            minutes,
        )
    await session.flush()
    return QuotaWorkspaceFixture(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        owner_id=owner_id,
        subscription_id=subscription_id,
        period_start=period_start,
        period_end=period_end,
    )


async def create_enterprise_workspace_subscription(
    session: AsyncSession,
    *,
    workspace_count: int = 1,
) -> QuotaWorkspaceFixture:
    tenant_id = uuid4()
    owner_id = uuid4()
    primary_workspace_id = uuid4()
    subscription_id = uuid4()
    period_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start + timedelta(days=31)
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
                'Enterprise Quota Test',
                'eu-central',
                'pool',
                'active'
            )
            """
        ),
        {"tenant_id": str(tenant_id), "slug": f"ent-{tenant_id.hex[:8]}"},
    )
    await set_tenant(session, tenant_id)
    await session.execute(
        text(
            """
            INSERT INTO users (id, email, tenant_id, status)
            VALUES (:owner_id, :email, :tenant_id, 'active')
            """
        ),
        {
            "owner_id": str(owner_id),
            "email": f"enterprise-{owner_id.hex}@example.test",
            "tenant_id": str(tenant_id),
        },
    )
    for index in range(workspace_count):
        workspace_id = primary_workspace_id if index == 0 else uuid4()
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
                "name": f"Enterprise {index}",
                "owner_id": str(owner_id),
                "tenant_id": str(tenant_id),
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO workspaces_memberships (workspace_id, user_id, tenant_id, role)
                VALUES (:workspace_id, :owner_id, :tenant_id, 'owner')
                """
            ),
            {
                "workspace_id": str(workspace_id),
                "owner_id": str(owner_id),
                "tenant_id": str(tenant_id),
            },
        )
    await session.execute(
        text(
            """
            INSERT INTO subscriptions (
                id,
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
                :subscription_id,
                :tenant_id,
                'tenant',
                :tenant_id,
                p.id,
                1,
                'active',
                :period_start,
                :period_end
              FROM plans p
             WHERE p.slug = 'enterprise'
            """
        ),
        {
            "subscription_id": str(subscription_id),
            "tenant_id": str(tenant_id),
            "period_start": period_start,
            "period_end": period_end,
        },
    )
    await session.flush()
    return QuotaWorkspaceFixture(
        tenant_id=tenant_id,
        workspace_id=primary_workspace_id,
        owner_id=owner_id,
        subscription_id=subscription_id,
        period_start=period_start,
        period_end=period_end,
    )


async def set_subscription_period(
    session: AsyncSession,
    *,
    subscription_id: UUID,
    period_start: datetime,
    period_end: datetime,
) -> None:
    await session.execute(
        text(
            """
            UPDATE subscriptions
               SET current_period_start = :period_start,
                   current_period_end = :period_end
             WHERE id = :subscription_id
            """
        ),
        {
            "subscription_id": str(subscription_id),
            "period_start": period_start,
            "period_end": period_end,
        },
    )
    await session.flush()


async def insert_usage_record(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    subscription_id: UUID,
    period_start: datetime,
    period_end: datetime,
    metric: str,
    quantity: Decimal,
    is_overage: bool = False,
) -> None:
    await _insert_usage(
        session,
        tenant_id,
        workspace_id,
        subscription_id,
        period_start,
        period_end,
        metric,
        quantity,
        is_overage=is_overage,
    )
    await session.flush()


async def insert_published_agents(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
    created_by: UUID,
    count: int,
) -> None:
    namespace_id = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO registry_namespaces (
                id,
                tenant_id,
                workspace_id,
                name,
                description,
                created_by
            )
            VALUES (
                :namespace_id,
                :tenant_id,
                :workspace_id,
                :name,
                'Quota test namespace',
                :created_by
            )
            """
        ),
        {
            "namespace_id": str(namespace_id),
            "tenant_id": str(tenant_id),
            "workspace_id": str(workspace_id),
            "name": f"quota-{namespace_id.hex[:8]}",
            "created_by": str(created_by),
        },
    )
    for index in range(count):
        profile_id = uuid4()
        local_name = f"agent-{index}-{profile_id.hex[:6]}"
        await session.execute(
            text(
                """
                INSERT INTO registry_agent_profiles (
                    id,
                    tenant_id,
                    workspace_id,
                    namespace_id,
                    local_name,
                    fqn,
                    display_name,
                    purpose,
                    role_types,
                    visibility_agents,
                    visibility_tools,
                    tags,
                    status,
                    maturity_level,
                    embedding_status,
                    needs_reindex,
                    created_by
                )
                VALUES (
                    :profile_id,
                    :tenant_id,
                    :workspace_id,
                    :namespace_id,
                    :local_name,
                    :fqn,
                    :display_name,
                    'Quota enforcement fixture',
                    '[]'::jsonb,
                    '[]'::jsonb,
                    '[]'::jsonb,
                    '[]'::jsonb,
                    'published',
                    0,
                    'pending',
                    false,
                    :created_by
                )
                """
            ),
            {
                "profile_id": str(profile_id),
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "namespace_id": str(namespace_id),
                "local_name": local_name,
                "fqn": f"quota.{local_name}",
                "display_name": f"Quota Agent {index}",
                "created_by": str(created_by),
            },
        )
    await session.flush()


async def _insert_usage(
    session: AsyncSession,
    tenant_id: UUID,
    workspace_id: UUID,
    subscription_id: UUID,
    period_start: datetime,
    period_end: datetime,
    metric: str,
    quantity: Decimal,
    *,
    is_overage: bool = False,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO usage_records (
                tenant_id,
                workspace_id,
                subscription_id,
                metric,
                period_start,
                period_end,
                quantity,
                is_overage
            )
            VALUES (
                :tenant_id,
                :workspace_id,
                :subscription_id,
                :metric,
                :period_start,
                :period_end,
                :quantity,
                :is_overage
            )
            """
        ),
        {
            "tenant_id": str(tenant_id),
            "workspace_id": str(workspace_id),
            "subscription_id": str(subscription_id),
            "metric": metric,
            "period_start": period_start,
            "period_end": period_end,
            "quantity": quantity,
            "is_overage": is_overage,
        },
    )
