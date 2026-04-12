from __future__ import annotations

from platform.evaluation.schemas import EvalRunSummaryDTO
from typing import Protocol
from uuid import UUID


class EvalSuiteServiceInterface(Protocol):
    async def get_run_summary(self, run_id: UUID) -> EvalRunSummaryDTO: ...

    async def get_latest_agent_score(
        self,
        agent_fqn: str,
        eval_set_id: UUID,
        workspace_id: UUID,
    ) -> float | None: ...
