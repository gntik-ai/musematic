from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.model_catalog.models import (
    InjectionDefensePattern,
    ModelCard,
    ModelCatalogEntry,
    ModelFallbackPolicy,
    ModelProviderCredential,
)
from typing import TypeVar
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class ModelCatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, item: T) -> T:
        self.session.add(item)
        await self.session.flush()
        return item

    async def get_entry(self, entry_id: UUID) -> ModelCatalogEntry | None:
        return await self.session.get(ModelCatalogEntry, entry_id)

    async def get_entry_by_provider_model(
        self,
        provider: str,
        model_id: str,
    ) -> ModelCatalogEntry | None:
        result = await self.session.execute(
            select(ModelCatalogEntry)
            .where(ModelCatalogEntry.provider == provider)
            .where(ModelCatalogEntry.model_id == model_id)
        )
        return result.scalar_one_or_none()

    async def list_entries(
        self,
        *,
        provider: str | None = None,
        status: str | None = None,
    ) -> list[ModelCatalogEntry]:
        statement = select(ModelCatalogEntry).order_by(
            ModelCatalogEntry.provider.asc(),
            ModelCatalogEntry.model_id.asc(),
        )
        if provider is not None:
            statement = statement.where(ModelCatalogEntry.provider == provider)
        if status is not None:
            statement = statement.where(ModelCatalogEntry.status == status)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_card_by_entry_id(self, entry_id: UUID) -> ModelCard | None:
        result = await self.session.execute(
            select(ModelCard).where(ModelCard.catalog_entry_id == entry_id)
        )
        return result.scalar_one_or_none()

    async def list_card_history(self, entry_id: UUID) -> list[ModelCard]:
        result = await self.session.execute(
            select(ModelCard)
            .where(ModelCard.catalog_entry_id == entry_id)
            .order_by(ModelCard.revision.desc())
        )
        return list(result.scalars().all())

    async def list_entries_missing_cards(
        self,
        *,
        older_than_days: int = 7,
    ) -> list[ModelCatalogEntry]:
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        result = await self.session.execute(
            select(ModelCatalogEntry)
            .outerjoin(ModelCard, ModelCard.catalog_entry_id == ModelCatalogEntry.id)
            .where(ModelCatalogEntry.status == "approved")
            .where(ModelCatalogEntry.approved_at < cutoff)
            .where(ModelCard.id.is_(None))
        )
        return list(result.scalars().all())

    async def list_expired_approved_entries(
        self,
        *,
        now: datetime | None = None,
    ) -> list[ModelCatalogEntry]:
        result = await self.session.execute(
            select(ModelCatalogEntry)
            .where(ModelCatalogEntry.status == "approved")
            .where(ModelCatalogEntry.approval_expires_at < (now or datetime.now(UTC)))
        )
        return list(result.scalars().all())

    async def get_fallback_policy_for_scope(
        self,
        *,
        scope_type: str,
        scope_id: UUID | None,
        primary_model_id: UUID,
    ) -> ModelFallbackPolicy | None:
        result = await self.session.execute(
            select(ModelFallbackPolicy)
            .where(ModelFallbackPolicy.scope_type == scope_type)
            .where(ModelFallbackPolicy.scope_id == scope_id)
            .where(ModelFallbackPolicy.primary_model_id == primary_model_id)
            .order_by(ModelFallbackPolicy.created_at.desc())
        )
        return result.scalars().first()

    async def get_fallback_policy(self, policy_id: UUID) -> ModelFallbackPolicy | None:
        return await self.session.get(ModelFallbackPolicy, policy_id)

    async def list_fallback_policies(
        self,
        *,
        primary_model_id: UUID | None = None,
        scope_type: str | None = None,
    ) -> list[ModelFallbackPolicy]:
        statement = select(ModelFallbackPolicy).order_by(ModelFallbackPolicy.created_at.desc())
        if primary_model_id is not None:
            statement = statement.where(ModelFallbackPolicy.primary_model_id == primary_model_id)
        if scope_type is not None:
            statement = statement.where(ModelFallbackPolicy.scope_type == scope_type)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def delete_fallback_policy(self, policy: ModelFallbackPolicy) -> None:
        await self.session.delete(policy)
        await self.session.flush()

    async def get_credential_by_workspace_provider(
        self,
        workspace_id: UUID,
        provider: str,
    ) -> ModelProviderCredential | None:
        result = await self.session.execute(
            select(ModelProviderCredential)
            .where(ModelProviderCredential.workspace_id == workspace_id)
            .where(ModelProviderCredential.provider == provider)
        )
        return result.scalar_one_or_none()

    async def get_credential(self, credential_id: UUID) -> ModelProviderCredential | None:
        return await self.session.get(ModelProviderCredential, credential_id)

    async def list_credentials(
        self,
        *,
        workspace_id: UUID | None = None,
        provider: str | None = None,
    ) -> list[ModelProviderCredential]:
        statement = select(ModelProviderCredential).order_by(
            ModelProviderCredential.workspace_id.asc(),
            ModelProviderCredential.provider.asc(),
        )
        if workspace_id is not None:
            statement = statement.where(ModelProviderCredential.workspace_id == workspace_id)
        if provider is not None:
            statement = statement.where(ModelProviderCredential.provider == provider)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def delete_credential(self, credential: ModelProviderCredential) -> None:
        await self.session.delete(credential)
        await self.session.flush()

    async def list_injection_patterns_for_layer(
        self,
        layer: str,
        *,
        workspace_id: UUID | None = None,
    ) -> list[InjectionDefensePattern]:
        statement = select(InjectionDefensePattern).where(InjectionDefensePattern.layer == layer)
        if workspace_id is None:
            statement = statement.where(InjectionDefensePattern.workspace_id.is_(None))
        else:
            statement = statement.where(
                or_(
                    InjectionDefensePattern.workspace_id.is_(None),
                    InjectionDefensePattern.workspace_id == workspace_id,
                )
            )
        result = await self.session.execute(
            statement.order_by(
                InjectionDefensePattern.workspace_id.asc().nullsfirst(),
                InjectionDefensePattern.severity.desc(),
                InjectionDefensePattern.pattern_name.asc(),
            )
        )
        return list(result.scalars().all())

    async def get_injection_pattern(self, pattern_id: UUID) -> InjectionDefensePattern | None:
        return await self.session.get(InjectionDefensePattern, pattern_id)

    async def list_injection_patterns(
        self,
        *,
        layer: str | None = None,
        workspace_id: UUID | None = None,
    ) -> list[InjectionDefensePattern]:
        statement = select(InjectionDefensePattern)
        if layer is not None:
            statement = statement.where(InjectionDefensePattern.layer == layer)
        if workspace_id is not None:
            statement = statement.where(
                or_(
                    InjectionDefensePattern.workspace_id.is_(None),
                    InjectionDefensePattern.workspace_id == workspace_id,
                )
            )
        result = await self.session.execute(
            statement.order_by(
                InjectionDefensePattern.layer.asc(),
                InjectionDefensePattern.pattern_name.asc(),
            )
        )
        return list(result.scalars().all())

    async def delete_injection_pattern(self, pattern: InjectionDefensePattern) -> None:
        await self.session.delete(pattern)
        await self.session.flush()

    async def delete_injection_findings_before(self, _cutoff: datetime) -> int:
        # Telemetry findings are currently in-process, not DB-backed.
        del _cutoff
        return 0
