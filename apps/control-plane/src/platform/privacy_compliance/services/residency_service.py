from __future__ import annotations

import json
from platform.privacy_compliance.events import (
    PrivacyEventPublisher,
    PrivacyEventType,
    ResidencyPayload,
    utcnow,
)
from platform.privacy_compliance.exceptions import ResidencyViolation
from platform.privacy_compliance.models import PrivacyResidencyConfig
from platform.privacy_compliance.repository import PrivacyComplianceRepository
from uuid import UUID


class ResidencyService:
    def __init__(
        self,
        *,
        repository: PrivacyComplianceRepository,
        event_publisher: PrivacyEventPublisher,
        redis_client: object | None = None,
        ttl_seconds: int = 60,
    ) -> None:
        self.repository = repository
        self.events = event_publisher
        self.redis = redis_client
        self.ttl_seconds = ttl_seconds
        self._cache: dict[UUID, PrivacyResidencyConfig | None] = {}

    async def get_config(self, workspace_id: UUID) -> PrivacyResidencyConfig | None:
        return await self.repository.get_residency_config(workspace_id)

    async def get_cached(self, workspace_id: UUID) -> PrivacyResidencyConfig | None:
        if workspace_id in self._cache:
            return self._cache[workspace_id]
        config = await self.get_config(workspace_id)
        self._cache[workspace_id] = config
        return config

    async def set_config(
        self,
        workspace_id: UUID,
        region_code: str,
        allowed_transfer_regions: list[str],
        *,
        actor: UUID,
    ) -> PrivacyResidencyConfig:
        config = await self.repository.upsert_residency_config(
            workspace_id=workspace_id,
            region_code=region_code,
            allowed_transfer_regions=allowed_transfer_regions,
        )
        self._cache.pop(workspace_id, None)
        await self.events.publish(
            PrivacyEventType.residency_configured,
            ResidencyPayload(
                workspace_id=workspace_id,
                region_code=region_code,
                allowed_transfer_regions=allowed_transfer_regions,
                actor_id=actor,
                occurred_at=utcnow(),
            ),
            key=str(workspace_id),
        )
        return config

    async def delete_config(self, workspace_id: UUID, *, actor: UUID) -> None:
        await self.repository.delete_residency_config(workspace_id)
        self._cache.pop(workspace_id, None)
        await self.events.publish(
            PrivacyEventType.residency_removed,
            ResidencyPayload(workspace_id=workspace_id, actor_id=actor, occurred_at=utcnow()),
            key=str(workspace_id),
        )

    async def enforce(self, workspace_id: UUID, origin_region: str | None) -> None:
        config = await self.get_cached(workspace_id)
        if config is None:
            return
        origin = origin_region or "unknown"
        allowed = list(config.allowed_transfer_regions)
        if origin == config.region_code or origin in allowed:
            return
        await self.events.publish(
            PrivacyEventType.residency_violated,
            ResidencyPayload(
                workspace_id=workspace_id,
                region_code=config.region_code,
                origin_region=origin,
                allowed_transfer_regions=allowed,
                occurred_at=utcnow(),
            ),
            key=str(workspace_id),
        )
        raise ResidencyViolation(
            workspace_id=workspace_id,
            origin_region=origin,
            required_region=config.region_code,
            allowed_transfer_regions=allowed,
        )

    @staticmethod
    def _cache_payload(config: PrivacyResidencyConfig | None) -> str:
        if config is None:
            return "null"
        return json.dumps(
            {
                "workspace_id": str(config.workspace_id),
                "region_code": config.region_code,
                "allowed_transfer_regions": list(config.allowed_transfer_regions),
            },
            sort_keys=True,
        )

