from __future__ import annotations

import json
from platform.audit.service import AuditChainService
from platform.multi_region_ops.exceptions import (
    ActiveActiveConfigurationRefusedError,
    RegionNotFoundError,
)
from platform.multi_region_ops.models import RegionConfig
from platform.multi_region_ops.repository import MultiRegionOpsRepository
from platform.multi_region_ops.schemas import RegionConfigCreateRequest, RegionConfigUpdateRequest
from typing import Any
from uuid import UUID, uuid4


class RegionService:
    def __init__(
        self,
        *,
        repository: MultiRegionOpsRepository,
        audit_chain_service: AuditChainService | None = None,
    ) -> None:
        self.repository = repository
        self.audit_chain_service = audit_chain_service

    async def create(
        self,
        payload: RegionConfigCreateRequest,
        *,
        by_user_id: UUID | None = None,
    ) -> RegionConfig:
        await self._refuse_second_primary(
            region_role=payload.region_role.value,
            enabled=payload.enabled,
        )
        region = await self.repository.insert_region(
            region_code=payload.region_code,
            region_role=payload.region_role.value,
            endpoint_urls=payload.endpoint_urls,
            rpo_target_minutes=payload.rpo_target_minutes,
            rto_target_minutes=payload.rto_target_minutes,
            enabled=payload.enabled,
        )
        await self._audit(
            "multi_region_ops.region.created",
            {
                "region_id": str(region.id),
                "region_code": region.region_code,
                "region_role": region.region_role,
                "enabled": region.enabled,
                "actor_id": str(by_user_id) if by_user_id else None,
            },
        )
        return region

    async def update(
        self,
        region_id: UUID,
        payload: RegionConfigUpdateRequest,
        *,
        by_user_id: UUID | None = None,
    ) -> RegionConfig:
        existing = await self.repository.get_region(region_id)
        if existing is None:
            raise RegionNotFoundError(region_id)
        next_role = (
            payload.region_role.value if payload.region_role is not None else existing.region_role
        )
        next_enabled = payload.enabled if payload.enabled is not None else existing.enabled
        await self._refuse_second_primary(
            region_role=next_role,
            enabled=next_enabled,
            exclude_region_id=region_id,
        )
        updates = payload.model_dump(exclude_unset=True)
        if payload.region_role is not None:
            updates["region_role"] = payload.region_role.value
        region = await self.repository.update_region(region_id, **updates)
        if region is None:
            raise RegionNotFoundError(region_id)
        await self._audit(
            "multi_region_ops.region.updated",
            {
                "region_id": str(region.id),
                "region_code": region.region_code,
                "region_role": region.region_role,
                "enabled": region.enabled,
                "actor_id": str(by_user_id) if by_user_id else None,
            },
        )
        return region

    async def enable(self, region_id: UUID, *, by_user_id: UUID | None = None) -> RegionConfig:
        existing = await self.repository.get_region(region_id)
        if existing is None:
            raise RegionNotFoundError(region_id)
        await self._refuse_second_primary(
            region_role=existing.region_role,
            enabled=True,
            exclude_region_id=region_id,
        )
        region = await self.repository.update_region(region_id, enabled=True)
        if region is None:
            raise RegionNotFoundError(region_id)
        await self._audit(
            "multi_region_ops.region.enabled",
            {
                "region_id": str(region.id),
                "region_code": region.region_code,
                "actor_id": str(by_user_id) if by_user_id else None,
            },
        )
        return region

    async def disable(self, region_id: UUID, *, by_user_id: UUID | None = None) -> RegionConfig:
        region = await self.repository.update_region(region_id, enabled=False)
        if region is None:
            raise RegionNotFoundError(region_id)
        await self._audit(
            "multi_region_ops.region.disabled",
            {
                "region_id": str(region.id),
                "region_code": region.region_code,
                "actor_id": str(by_user_id) if by_user_id else None,
            },
        )
        return region

    async def delete(self, region_id: UUID, *, by_user_id: UUID | None = None) -> None:
        region = await self.repository.get_region(region_id)
        if region is None:
            raise RegionNotFoundError(region_id)
        if await self.repository.has_dependent_plans(region.region_code):
            raise ValueError("Cannot delete a region referenced by failover plans")
        await self.repository.delete_region(region_id)
        await self._audit(
            "multi_region_ops.region.deleted",
            {
                "region_id": str(region_id),
                "region_code": region.region_code,
                "actor_id": str(by_user_id) if by_user_id else None,
            },
        )

    async def get(self, region_id: UUID) -> RegionConfig:
        region = await self.repository.get_region(region_id)
        if region is None:
            raise RegionNotFoundError(region_id)
        return region

    async def get_by_code(self, code: str) -> RegionConfig:
        region = await self.repository.get_region_by_code(code)
        if region is None:
            raise RegionNotFoundError(code)
        return region

    async def list(self, *, enabled_only: bool = False) -> list[RegionConfig]:
        return await self.repository.list_regions(enabled_only=enabled_only)

    async def _refuse_second_primary(
        self,
        *,
        region_role: str,
        enabled: bool,
        exclude_region_id: UUID | None = None,
    ) -> None:
        if region_role != "primary" or not enabled:
            return
        active_primaries = await self.repository.count_active_primaries(
            exclude_region_id=exclude_region_id
        )
        if active_primaries > 0:
            raise ActiveActiveConfigurationRefusedError()

    async def _audit(self, event_source: str, payload: dict[str, Any]) -> None:
        if self.audit_chain_service is None:
            return
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        await self.audit_chain_service.append(uuid4(), event_source, canonical)
