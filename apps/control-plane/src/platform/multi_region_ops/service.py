from __future__ import annotations

from platform.multi_region_ops.models import MaintenanceWindow
from platform.multi_region_ops.services.capacity_service import CapacityService
from platform.multi_region_ops.services.failover_service import FailoverService
from platform.multi_region_ops.services.maintenance_mode_service import MaintenanceModeService
from platform.multi_region_ops.services.region_service import RegionService
from platform.multi_region_ops.services.replication_monitor import ReplicationMonitor
from uuid import UUID


class MultiRegionOpsService:
    def __init__(
        self,
        *,
        region_service: RegionService,
        replication_monitor: ReplicationMonitor,
        failover_service: FailoverService,
        maintenance_mode_service: MaintenanceModeService,
        capacity_service: CapacityService,
    ) -> None:
        self.region_service = region_service
        self.replication_monitor = replication_monitor
        self.failover_service = failover_service
        self.maintenance_mode_service = maintenance_mode_service
        self.capacity_service = capacity_service

    async def handle_workspace_archived(self, workspace_id: UUID) -> None:
        del workspace_id

    async def get_active_window(self) -> MaintenanceWindow | None:
        return await self.maintenance_mode_service.get_active_window()
