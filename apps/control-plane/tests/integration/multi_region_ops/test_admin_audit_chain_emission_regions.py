from __future__ import annotations

import json
from platform.multi_region_ops.schemas import RegionConfigUpdateRequest, RegionRole
from platform.multi_region_ops.services.region_service import RegionService

import pytest

from tests.integration.multi_region_ops.support import (
    MultiRegionMemoryRepository,
    RecordingAudit,
    superadmin_create_payload,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_region_admin_mutations_emit_redacted_audit_entries() -> None:
    repository = MultiRegionMemoryRepository()
    audit = RecordingAudit()
    service = RegionService(
        repository=repository,  # type: ignore[arg-type]
        audit_chain_service=audit,  # type: ignore[arg-type]
    )

    region = await service.create(superadmin_create_payload("eu-west", RegionRole.primary))
    await service.update(region.id, RegionConfigUpdateRequest(rpo_target_minutes=5))
    await service.disable(region.id)
    await service.enable(region.id)
    await service.delete(region.id)

    event_sources = [entry[1] for entry in audit.entries]
    assert event_sources == [
        "multi_region_ops.region.created",
        "multi_region_ops.region.updated",
        "multi_region_ops.region.disabled",
        "multi_region_ops.region.enabled",
        "multi_region_ops.region.deleted",
    ]
    decoded = [json.loads(entry[2].decode()) for entry in audit.entries]
    assert all("region_id" in payload for payload in decoded)
    assert "secret/data/multi-region/postgres" not in "\n".join(
        entry[2].decode() for entry in audit.entries
    )


async def test_region_admin_mutation_fails_when_audit_chain_write_fails() -> None:
    service = RegionService(
        repository=MultiRegionMemoryRepository(),  # type: ignore[arg-type]
        audit_chain_service=RecordingAudit(fail=True),  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="audit chain unavailable"):
        await service.create(superadmin_create_payload("eu-west", RegionRole.primary))
