from __future__ import annotations

from platform.testing.models import CoordinationTestResult
from typing import Protocol
from uuid import UUID


class CoordinationTestServiceInterface(Protocol):
    async def run_coordination_test(
        self,
        fleet_id: UUID,
        execution_id: UUID,
        workspace_id: UUID,
    ) -> CoordinationTestResult: ...
