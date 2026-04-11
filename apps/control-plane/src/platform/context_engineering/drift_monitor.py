from __future__ import annotations

from platform.context_engineering.service import ContextEngineeringService


class DriftMonitorTask:
    def __init__(self, service: ContextEngineeringService) -> None:
        self.service = service

    async def run(self) -> int:
        return await self.service.run_drift_analysis()
