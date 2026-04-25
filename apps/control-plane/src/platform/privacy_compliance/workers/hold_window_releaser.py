from __future__ import annotations

from platform.privacy_compliance.services.dsr_service import DSRService


class HoldWindowReleaser:
    def __init__(self, service: DSRService) -> None:
        self.service = service

    async def run_once(self) -> int:
        released = await self.service.release_due_holds()
        return len(released)

