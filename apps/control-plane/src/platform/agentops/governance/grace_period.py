from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from platform.agentops.repository import AgentOpsRepository
from platform.agentops.retirement.workflow import RetirementManager
from typing import Any


class GracePeriodScanner:
    def __init__(
        self,
        *,
        repository: AgentOpsRepository,
        retirement_manager: RetirementManager,
        trust_service: Any | None,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.retirement_manager = retirement_manager
        self.trust_service = trust_service
        self._now_factory = now_factory or (lambda: datetime.now(UTC))

    async def retirement_grace_period_scanner_task(self) -> None:
        for workflow in await self.repository.list_due_retirements(self._now()):
            if workflow.high_impact_flag and not workflow.operator_confirmed:
                continue
            await self.retirement_manager.retire_agent(workflow.id)

    async def recertification_grace_period_scanner_task(self) -> None:
        if self.trust_service is None:
            return
        expire_stale = getattr(self.trust_service, "expire_stale_certifications", None)
        if callable(expire_stale):
            await expire_stale()

    def _now(self) -> datetime:
        return self._now_factory()
