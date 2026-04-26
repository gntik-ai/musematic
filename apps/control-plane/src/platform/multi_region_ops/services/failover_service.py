from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from platform.audit.service import AuditChainService
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.multi_region_ops.constants import REDIS_KEY_FAILOVER_LOCK_TEMPLATE
from platform.multi_region_ops.events import (
    MultiRegionOpsEventType,
    RegionFailoverCompletedPayload,
    RegionFailoverInitiatedPayload,
    publish_multi_region_ops_event,
)
from platform.multi_region_ops.exceptions import (
    FailoverInProgressError,
    FailoverPlanNotFoundError,
    FailoverRunNotFoundError,
)
from platform.multi_region_ops.models import FailoverPlan, FailoverPlanRun
from platform.multi_region_ops.repository import MultiRegionOpsRepository
from platform.multi_region_ops.schemas import (
    FailoverPlanCreateRequest,
    FailoverPlanRunKind,
    FailoverPlanUpdateRequest,
)
from platform.multi_region_ops.services.failover_steps import default_step_adapters
from platform.multi_region_ops.services.failover_steps.base import FailoverStepAdapter, StepOutcome
from typing import Any
from uuid import UUID, uuid4


class FailoverService:
    def __init__(
        self,
        *,
        repository: MultiRegionOpsRepository,
        settings: PlatformSettings,
        redis_client: AsyncRedisClient | None = None,
        producer: EventProducer | None = None,
        audit_chain_service: AuditChainService | None = None,
        step_adapters: dict[str, FailoverStepAdapter] | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.redis_client = redis_client
        self.producer = producer
        self.audit_chain_service = audit_chain_service
        self.step_adapters = step_adapters or default_step_adapters()

    async def create_plan(
        self,
        payload: FailoverPlanCreateRequest,
        *,
        by_user_id: UUID | None = None,
    ) -> FailoverPlan:
        await self._require_enabled_region(payload.from_region)
        await self._require_enabled_region(payload.to_region)
        plan = await self.repository.insert_plan(
            name=payload.name,
            from_region=payload.from_region,
            to_region=payload.to_region,
            steps=[step.model_dump(mode="json") for step in payload.steps],
            runbook_url=payload.runbook_url,
            created_by=by_user_id,
        )
        await self._audit(
            "multi_region_ops.failover_plan.created",
            {"plan_id": str(plan.id), "actor_id": str(by_user_id) if by_user_id else None},
        )
        return plan

    async def update_plan(
        self,
        plan_id: UUID,
        payload: FailoverPlanUpdateRequest,
        *,
        by_user_id: UUID | None = None,
    ) -> FailoverPlan:
        current = await self.repository.get_plan(plan_id)
        if current is None:
            raise FailoverPlanNotFoundError(plan_id)
        from_region = payload.from_region or current.from_region
        to_region = payload.to_region or current.to_region
        await self._require_enabled_region(from_region)
        await self._require_enabled_region(to_region)
        updates = payload.model_dump(exclude={"expected_version"}, exclude_unset=True, mode="json")
        plan = await self.repository.update_plan(
            plan_id,
            expected_version=payload.expected_version,
            updates=updates,
        )
        if plan is None:
            raise FailoverPlanNotFoundError(plan_id)
        await self._audit(
            "multi_region_ops.failover_plan.updated",
            {"plan_id": str(plan.id), "actor_id": str(by_user_id) if by_user_id else None},
        )
        return plan

    async def delete_plan(self, plan_id: UUID, *, by_user_id: UUID | None = None) -> None:
        if await self.repository.has_in_progress_runs(plan_id):
            raise FailoverInProgressError(from_region="unknown", to_region="unknown")
        if not await self.repository.delete_plan(plan_id):
            raise FailoverPlanNotFoundError(plan_id)
        await self._audit(
            "multi_region_ops.failover_plan.deleted",
            {"plan_id": str(plan_id), "actor_id": str(by_user_id) if by_user_id else None},
        )

    async def rehearse(
        self,
        plan_id: UUID,
        *,
        by_user_id: UUID | None = None,
        reason: str | None = None,
    ) -> FailoverPlanRun:
        return await self._run_plan(
            plan_id,
            run_kind=FailoverPlanRunKind.rehearsal.value,
            dry_run=True,
            by_user_id=by_user_id,
            reason=reason,
        )

    async def execute(
        self,
        plan_id: UUID,
        *,
        by_user_id: UUID | None = None,
        reason: str | None = None,
    ) -> FailoverPlanRun:
        return await self._run_plan(
            plan_id,
            run_kind=FailoverPlanRunKind.production.value,
            dry_run=False,
            by_user_id=by_user_id,
            reason=reason,
        )

    async def get_plan(self, plan_id: UUID) -> FailoverPlan:
        plan = await self.repository.get_plan(plan_id)
        if plan is None:
            raise FailoverPlanNotFoundError(plan_id)
        return plan

    async def list_plans(
        self,
        *,
        from_region: str | None = None,
        to_region: str | None = None,
    ) -> list[FailoverPlan]:
        return await self.repository.list_plans(from_region=from_region, to_region=to_region)

    async def get_run(self, run_id: UUID) -> FailoverPlanRun:
        run = await self.repository.get_plan_run(run_id)
        if run is None:
            raise FailoverRunNotFoundError(run_id)
        return run

    async def list_runs(self, plan_id: UUID) -> list[FailoverPlanRun]:
        return await self.repository.list_plan_runs(plan_id)

    def is_stale(self, plan: FailoverPlan, *, now: datetime | None = None) -> bool:
        if plan.tested_at is None:
            return True
        resolved_now = now or datetime.now(UTC)
        age = resolved_now - plan.tested_at
        return age.days > self.settings.multi_region_ops.failover_plan_rehearsal_staleness_days

    async def acquire_failover_lock(self, from_region: str, to_region: str) -> str | None:
        if self.redis_client is None:
            return str(uuid4())
        key = REDIS_KEY_FAILOVER_LOCK_TEMPLATE.format(
            from_region=from_region,
            to_region=to_region,
        )
        token = str(uuid4())
        client = await self.redis_client._get_client()
        acquired = await client.set(
            key,
            token,
            ex=self.settings.multi_region_ops.failover_lock_max_seconds,
            nx=True,
        )
        return token if acquired else None

    async def release_failover_lock(self, from_region: str, to_region: str, token: str) -> bool:
        if self.redis_client is None:
            return True
        key = REDIS_KEY_FAILOVER_LOCK_TEMPLATE.format(
            from_region=from_region,
            to_region=to_region,
        )
        current = await self.redis_client.get(key)
        if current is None or current.decode() != token:
            return False
        await self.redis_client.delete(key)
        return True

    async def _run_plan(
        self,
        plan_id: UUID,
        *,
        run_kind: str,
        dry_run: bool,
        by_user_id: UUID | None,
        reason: str | None,
    ) -> FailoverPlanRun:
        plan = await self.get_plan(plan_id)
        token = await self.acquire_failover_lock(plan.from_region, plan.to_region)
        if token is None:
            running = await self.repository.get_latest_in_progress_run(
                from_region=plan.from_region,
                to_region=plan.to_region,
            )
            raise FailoverInProgressError(
                from_region=plan.from_region,
                to_region=plan.to_region,
                running_run_id=str(running.id) if running else None,
            )
        run = await self.repository.insert_plan_run(
            plan_id=plan.id,
            run_kind=run_kind,
            initiated_by=by_user_id,
            reason=reason,
            lock_token=token,
        )
        correlation_ctx = CorrelationContext(correlation_id=uuid4())
        started = time.perf_counter()
        await publish_multi_region_ops_event(
            self.producer,
            MultiRegionOpsEventType.region_failover_initiated,
            RegionFailoverInitiatedPayload(
                plan_id=plan.id,
                run_id=run.id,
                from_region=plan.from_region,
                to_region=plan.to_region,
                run_kind=run_kind,
                initiated_by=by_user_id,
            ),
            correlation_ctx,
        )
        final_outcome = "succeeded"
        try:
            for index, step in enumerate(plan.steps):
                outcome = await self._execute_step(plan, run, index, step, dry_run=dry_run)
                await self.repository.append_plan_run_step_outcome(run.id, outcome)
                if outcome["outcome"] == "failed":
                    final_outcome = "failed"
                    await self._record_aborted_steps(plan, run, index + 1)
                    break
            ended_at = datetime.now(UTC)
            await self.repository.update_plan_run_outcome(
                run.id, outcome=final_outcome, ended_at=ended_at
            )
            if final_outcome == "succeeded" and run_kind == "rehearsal":
                await self.repository.mark_plan_tested(plan.id, ended_at)
            if final_outcome == "succeeded" and run_kind == "production":
                await self.repository.mark_plan_executed(plan.id, ended_at)
            run = await self.get_run(run.id)
            await publish_multi_region_ops_event(
                self.producer,
                MultiRegionOpsEventType.region_failover_completed,
                RegionFailoverCompletedPayload(
                    plan_id=plan.id,
                    run_id=run.id,
                    outcome=final_outcome,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    step_outcomes_summary=self._summarize_steps(run.step_outcomes),
                ),
                correlation_ctx,
            )
            await self._audit(
                "multi_region_ops.failover_plan.run",
                {
                    "plan_id": str(plan.id),
                    "run_id": str(run.id),
                    "run_kind": run_kind,
                    "outcome": final_outcome,
                    "actor_id": str(by_user_id) if by_user_id else None,
                },
            )
            return run
        finally:
            await self.release_failover_lock(plan.from_region, plan.to_region, token)

    async def _execute_step(
        self,
        plan: FailoverPlan,
        run: FailoverPlanRun,
        index: int,
        step: dict[str, Any],
        *,
        dry_run: bool,
    ) -> dict[str, Any]:
        kind = str(step.get("kind"))
        adapter = self.step_adapters.get(kind)
        name = str(step.get("name") or kind)
        if adapter is None:
            outcome = StepOutcome(
                kind=kind,
                name=name,
                outcome="failed",
                error_detail=f"No adapter registered for {kind}",
            )
        else:
            started = time.perf_counter()
            try:
                outcome = await adapter.execute(
                    plan=plan,
                    run=run,
                    parameters=dict(step.get("parameters") or {}, name=name),
                    dry_run=dry_run,
                )
            except Exception as exc:
                outcome = StepOutcome(kind=kind, name=name, outcome="failed", error_detail=str(exc))
            outcome.duration_ms = max(
                outcome.duration_ms, int((time.perf_counter() - started) * 1000)
            )
        return {
            "step_index": index,
            "kind": outcome.kind,
            "name": outcome.name,
            "outcome": outcome.outcome,
            "duration_ms": outcome.duration_ms,
            "error_detail": outcome.error_detail,
        }

    async def _record_aborted_steps(
        self, plan: FailoverPlan, run: FailoverPlanRun, start: int
    ) -> None:
        for index, step in enumerate(plan.steps[start:], start=start):
            await self.repository.append_plan_run_step_outcome(
                run.id,
                {
                    "step_index": index,
                    "kind": str(step.get("kind")),
                    "name": str(step.get("name") or step.get("kind")),
                    "outcome": "aborted",
                    "duration_ms": 0,
                    "error_detail": "previous step failed",
                },
            )

    async def _require_enabled_region(self, code: str) -> None:
        region = await self.repository.get_region_by_code(code)
        if region is None or not region.enabled:
            raise ValueError(f"Region {code} is not enabled")

    async def _audit(self, event_source: str, payload: dict[str, Any]) -> None:
        if self.audit_chain_service is None:
            return
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        await self.audit_chain_service.append(uuid4(), event_source, canonical)

    @staticmethod
    def _summarize_steps(step_outcomes: list[dict[str, Any]]) -> dict[str, Any]:
        summary: dict[str, int] = {}
        for item in step_outcomes:
            outcome = str(item.get("outcome", "unknown"))
            summary[outcome] = summary.get(outcome, 0) + 1
        return summary
