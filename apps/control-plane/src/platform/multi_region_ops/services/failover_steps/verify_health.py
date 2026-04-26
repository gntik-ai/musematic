from __future__ import annotations

from platform.multi_region_ops.models import FailoverPlan, FailoverPlanRun
from platform.multi_region_ops.services.failover_steps.base import NoopStepAdapter, StepOutcome
from typing import Any

import httpx


class VerifyHealthStepAdapter(NoopStepAdapter):
    kind = "verify_health"
    default_name = "Verify health"

    async def execute(
        self,
        *,
        plan: FailoverPlan,
        run: FailoverPlanRun,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> StepOutcome:
        del plan, run, dry_run
        name = str(parameters.get("name") or self.default_name)
        url = parameters.get("url")
        if not isinstance(url, str) or not url:
            return StepOutcome(kind=self.kind, name=name, outcome="succeeded")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                response.raise_for_status()
        except Exception as exc:
            return StepOutcome(kind=self.kind, name=name, outcome="failed", error_detail=str(exc))
        return StepOutcome(kind=self.kind, name=name, outcome="succeeded")
