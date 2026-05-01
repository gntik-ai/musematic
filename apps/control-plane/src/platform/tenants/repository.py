from __future__ import annotations

from collections.abc import Sequence
from platform.tenants.models import Tenant
from uuid import UUID

from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession


class TenantsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        return await self.session.get(Tenant, tenant_id)

    async def get_by_slug(self, slug: str) -> Tenant | None:
        result = await self.session.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()

    async def get_by_subdomain(self, subdomain: str) -> Tenant | None:
        result = await self.session.execute(select(Tenant).where(Tenant.subdomain == subdomain))
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        kind: str | None = None,
        status: str | None = None,
        q: str | None = None,
        limit: int = 100,
    ) -> Sequence[Tenant]:
        statement: Select[tuple[Tenant]] = select(Tenant).order_by(Tenant.created_at.desc())
        if kind is not None:
            statement = statement.where(Tenant.kind == kind)
        if status is not None:
            statement = statement.where(Tenant.status == status)
        if q:
            pattern = f"%{q.lower()}%"
            statement = statement.where(
                (Tenant.slug.ilike(pattern)) | (Tenant.display_name.ilike(pattern))
            )
        result = await self.session.execute(statement.limit(min(limit, 100)))
        return result.scalars().all()

    async def create(self, tenant: Tenant) -> Tenant:
        self.session.add(tenant)
        await self.session.flush()
        return tenant

    async def update(self, tenant: Tenant, **values: object) -> Tenant:
        for field, value in values.items():
            setattr(tenant, field, value)
        await self.session.flush()
        return tenant

    async def delete(self, tenant: Tenant) -> None:
        await self.session.delete(tenant)
        await self.session.flush()

    async def delete_by_id(self, tenant_id: UUID) -> None:
        await self.session.execute(delete(Tenant).where(Tenant.id == tenant_id))
        await self.session.flush()
