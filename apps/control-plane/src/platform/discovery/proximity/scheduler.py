from __future__ import annotations

from platform.common.config import DiscoverySettings
from platform.discovery.service import DiscoveryService


async def workspace_proximity_recompute_task(
    service: DiscoveryService,
    settings: DiscoverySettings,
) -> None:
    del settings
    await service.workspace_proximity_recompute_task()
