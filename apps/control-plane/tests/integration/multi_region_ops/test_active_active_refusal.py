from __future__ import annotations

from platform.multi_region_ops.exceptions import ActiveActiveConfigurationRefusedError
from platform.multi_region_ops.models import RegionConfig
from platform.multi_region_ops.schemas import RegionConfigUpdateRequest, RegionRole
from platform.multi_region_ops.services.region_service import RegionService

import pytest

from tests.integration.multi_region_ops.support import (
    MultiRegionMemoryRepository,
    superadmin_create_payload,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_active_active_refused_by_service_and_database_metadata() -> None:
    repository = MultiRegionMemoryRepository()
    service = RegionService(repository=repository)  # type: ignore[arg-type]

    primary = await service.create(superadmin_create_payload("eu-west", RegionRole.primary))
    secondary = await service.create(superadmin_create_payload("us-east", RegionRole.secondary))

    with pytest.raises(ActiveActiveConfigurationRefusedError) as create_error:
        await service.create(superadmin_create_payload("ap-south", RegionRole.primary))
    assert "active-active considerations" in create_error.value.message
    assert create_error.value.details["runbook"].endswith("active-active-considerations.md")

    with pytest.raises(ActiveActiveConfigurationRefusedError):
        await service.update(
            secondary.id,
            RegionConfigUpdateRequest(region_role=RegionRole.primary),
        )

    primary.enabled = False
    promoted = await service.update(
        secondary.id,
        RegionConfigUpdateRequest(region_role=RegionRole.primary),
    )
    assert promoted.region_role == "primary"

    index_names = {item.name for item in RegionConfig.__table__.indexes}
    assert "uq_region_configs_single_enabled_primary" in index_names
