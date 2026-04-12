from __future__ import annotations

from platform.fleet_learning.adaptation import FleetAdaptationEngineService
from platform.fleet_learning.performance import FleetPerformanceProfileService
from platform.fleet_learning.personality import FleetPersonalityProfileService
from platform.fleet_learning.transfer import CrossFleetTransferService


class FleetLearningService:
    def __init__(
        self,
        *,
        performance_service: FleetPerformanceProfileService,
        adaptation_service: FleetAdaptationEngineService,
        transfer_service: CrossFleetTransferService,
        personality_service: FleetPersonalityProfileService,
    ) -> None:
        self.performance = performance_service
        self.adaptation = adaptation_service
        self.transfer = transfer_service
        self.personality = personality_service
