from __future__ import annotations

from platform.multi_region_ops.models import FailoverPlan, FailoverPlanRun
from typing import Any, Protocol

from pydantic import BaseModel


class StepOutcome(BaseModel):
    kind: str
    name: str
    outcome: str
    duration_ms: int = 0
    error_detail: str | None = None


class FailoverStepAdapter(Protocol):
    kind: str

    async def execute(
        self,
        *,
        plan: FailoverPlan,
        run: FailoverPlanRun,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> StepOutcome: ...


class NoopStepAdapter:
    kind = "custom"
    default_name = "Operator step"

    async def execute(
        self,
        *,
        plan: FailoverPlan,
        run: FailoverPlanRun,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> StepOutcome:
        del plan, run
        name = str(parameters.get("name") or self.default_name)
        if dry_run and _touches_production_routing(parameters):
            return StepOutcome(
                kind=self.kind,
                name=name,
                outcome="failed",
                error_detail="dry-run step may not touch production routing",
            )
        return StepOutcome(kind=self.kind, name=name, outcome="succeeded")


def _touches_production_routing(parameters: dict[str, Any]) -> bool:
    blocked_tokens = ("dns", "route", "routing", "production", "prod")
    for key, value in parameters.items():
        text = f"{key} {value}".lower()
        if any(token in text for token in blocked_tokens):
            return True
    return False
