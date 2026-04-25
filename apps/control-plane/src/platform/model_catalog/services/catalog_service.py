from __future__ import annotations

from datetime import UTC, datetime
from platform.audit.service import AuditChainService
from platform.common.audit_hook import audit_chain_hook
from platform.common.events.producer import EventProducer
from platform.common.exceptions import NotFoundError, ValidationError
from platform.model_catalog.events import (
    ModelCatalogUpdatedPayload,
    publish_model_catalog_updated,
)
from platform.model_catalog.models import ModelCatalogEntry
from platform.model_catalog.repository import ModelCatalogRepository
from platform.model_catalog.schemas import (
    BlockRequest,
    CatalogEntryCreate,
    CatalogEntryListResponse,
    CatalogEntryPatch,
    CatalogEntryResponse,
    DeprecateRequest,
    ReapproveRequest,
)
from uuid import UUID, uuid4


class CatalogService:
    def __init__(
        self,
        repository: ModelCatalogRepository,
        *,
        producer: EventProducer | None = None,
        audit_chain: AuditChainService | None = None,
    ) -> None:
        self.repository = repository
        self.producer = producer
        self.audit_chain = audit_chain

    async def create_entry(
        self,
        request: CatalogEntryCreate,
        *,
        approved_by: UUID,
    ) -> CatalogEntryResponse:
        existing = await self.repository.get_entry_by_provider_model(
            request.provider,
            request.model_id,
        )
        if existing is not None:
            raise ValidationError(
                "MODEL_CATALOG_DUPLICATE",
                "A catalogue entry already exists for this provider and model_id.",
                {"catalog_entry_id": str(existing.id)},
            )
        now = datetime.now(UTC)
        entry = await self.repository.add(
            ModelCatalogEntry(
                provider=request.provider,
                model_id=request.model_id,
                display_name=request.display_name,
                approved_use_cases=request.approved_use_cases,
                prohibited_use_cases=request.prohibited_use_cases,
                context_window=request.context_window,
                input_cost_per_1k_tokens=request.input_cost_per_1k_tokens,
                output_cost_per_1k_tokens=request.output_cost_per_1k_tokens,
                quality_tier=request.quality_tier,
                approved_by=approved_by,
                approved_at=now,
                approval_expires_at=request.approval_expires_at,
                status="approved",
                created_at=now,
                updated_at=now,
            )
        )
        await self._emit_update(entry, approved_by)
        return CatalogEntryResponse.model_validate(entry)

    async def list_entries(
        self,
        *,
        provider: str | None = None,
        status: str | None = None,
    ) -> CatalogEntryListResponse:
        items = await self.repository.list_entries(provider=provider, status=status)
        return CatalogEntryListResponse(
            items=[CatalogEntryResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def get_entry(self, entry_id: UUID) -> CatalogEntryResponse:
        return CatalogEntryResponse.model_validate(await self._get(entry_id))

    async def update_entry(
        self,
        entry_id: UUID,
        patch: CatalogEntryPatch,
        *,
        changed_by: UUID,
    ) -> CatalogEntryResponse:
        entry = await self._get(entry_id)
        updates = patch.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(entry, field, value)
        if updates:
            entry.updated_at = datetime.now(UTC)
            await self.repository.session.flush()
            await self._emit_update(entry, changed_by)
        return CatalogEntryResponse.model_validate(entry)

    async def block_entry(
        self,
        entry_id: UUID,
        request: BlockRequest,
        *,
        changed_by: UUID,
    ) -> CatalogEntryResponse:
        del request
        return await self._transition(entry_id, "blocked", changed_by=changed_by)

    async def deprecate_entry(
        self,
        entry_id: UUID,
        request: DeprecateRequest,
        *,
        changed_by: UUID | None,
    ) -> CatalogEntryResponse:
        del request
        return await self._transition(entry_id, "deprecated", changed_by=changed_by)

    async def reapprove_entry(
        self,
        entry_id: UUID,
        request: ReapproveRequest,
        *,
        changed_by: UUID,
    ) -> CatalogEntryResponse:
        entry = await self._get(entry_id)
        entry.status = "approved"
        entry.approved_by = changed_by
        entry.approved_at = datetime.now(UTC)
        entry.approval_expires_at = request.approval_expires_at
        entry.updated_at = datetime.now(UTC)
        await self.repository.session.flush()
        await self._emit_update(entry, changed_by)
        return CatalogEntryResponse.model_validate(entry)

    async def _transition(
        self,
        entry_id: UUID,
        status: str,
        *,
        changed_by: UUID | None,
    ) -> CatalogEntryResponse:
        entry = await self._get(entry_id)
        if entry.status == status:
            return CatalogEntryResponse.model_validate(entry)
        entry.status = status
        entry.updated_at = datetime.now(UTC)
        await self.repository.session.flush()
        await self._emit_update(entry, changed_by)
        return CatalogEntryResponse.model_validate(entry)

    async def _get(self, entry_id: UUID) -> ModelCatalogEntry:
        entry = await self.repository.get_entry(entry_id)
        if entry is None:
            raise NotFoundError("MODEL_CATALOG_ENTRY_NOT_FOUND", "Catalogue entry not found")
        return entry

    async def _emit_update(
        self,
        entry: ModelCatalogEntry,
        changed_by: UUID | None,
    ) -> None:
        payload = ModelCatalogUpdatedPayload(
            catalog_entry_id=entry.id,
            provider=entry.provider,
            model_id=entry.model_id,
            status=entry.status,
            changed_by=changed_by,
        )
        correlation_id = uuid4()
        await publish_model_catalog_updated(payload, correlation_id, self.producer)
        if self.audit_chain is not None:
            await audit_chain_hook(
                self.audit_chain,
                entry.id,
                "model_catalog",
                {
                    "event": "model.catalog.updated",
                    "catalog_entry_id": entry.id,
                    "provider": entry.provider,
                    "model_id": entry.model_id,
                    "status": entry.status,
                    "changed_by": changed_by,
                },
            )
