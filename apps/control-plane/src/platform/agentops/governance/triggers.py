from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.agentops.events import AgentOpsEventType, GovernanceEventPublisher
from platform.agentops.models import BaselineStatus, BehavioralBaseline
from platform.agentops.regression.detector import RegressionDetector
from platform.agentops.repository import AgentOpsRepository
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import EventEnvelope
from platform.evaluation.events import EvaluationEventType
from platform.evaluation.repository import EvaluationRepository
from typing import Any
from uuid import UUID

import numpy as np


class AgentOpsGovernanceTriggers:
    def __init__(
        self,
        *,
        repository: AgentOpsRepository,
        detector: RegressionDetector,
        evaluation_repository: EvaluationRepository,
        registry_service: Any | None,
        trust_service: Any | None = None,
        governance_publisher: GovernanceEventPublisher | None = None,
        agentops_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.detector = detector
        self.evaluation_repository = evaluation_repository
        self.registry_service = registry_service
        self.trust_service = trust_service
        self.governance_publisher = governance_publisher
        self.agentops_service = agentops_service
        self._seen_event_ids: set[str] = set()

    async def handle_evaluation_event(self, envelope: EventEnvelope) -> None:
        if envelope.event_type == EvaluationEventType.ate_run_completed.value:
            await self._handle_ate_completion(envelope, passed=True)
            return
        if envelope.event_type == EvaluationEventType.ate_run_failed.value:
            await self._handle_ate_completion(envelope, passed=False)
            return
        if envelope.event_type != EvaluationEventType.run_completed.value:
            return

        payload = envelope.payload
        run_id = payload.get("run_id")
        workspace_id = payload.get("workspace_id")
        if run_id is None or workspace_id is None:
            return

        run = await self.evaluation_repository.get_run(UUID(str(run_id)), UUID(str(workspace_id)))
        if run is None:
            return

        current_target = await self._current_target(run.agent_fqn, run.workspace_id)
        if current_target is None:
            return

        baseline = await self.repository.get_baseline_by_revision(current_target["revision_id"])
        if baseline is None:
            baseline = await self.repository.create_baseline(
                BehavioralBaseline(
                    workspace_id=run.workspace_id,
                    agent_fqn=run.agent_fqn,
                    revision_id=current_target["revision_id"],
                    baseline_window_start=datetime.now(UTC) - timedelta(days=30),
                    baseline_window_end=datetime.now(UTC),
                    status=BaselineStatus.pending,
                )
            )

        if baseline.status == BaselineStatus.pending:
            await self._materialize_baseline_if_ready(
                baseline=baseline,
                workspace_id=run.workspace_id,
            )
            return

        ready_baselines, _ = await self.repository.list_baselines(
            run.agent_fqn,
            run.workspace_id,
            limit=100,
        )
        comparison_target = next(
            (
                item
                for item in ready_baselines
                if item.status == BaselineStatus.ready and item.revision_id != baseline.revision_id
            ),
            None,
        )
        if comparison_target is None:
            return

        await self.detector.detect(
            new_revision_id=baseline.revision_id,
            baseline_revision_id=comparison_target.revision_id,
            agent_fqn=run.agent_fqn,
            workspace_id=run.workspace_id,
        )

    async def handle_agentops_event(self, envelope: EventEnvelope) -> None:
        if envelope.event_type == AgentOpsEventType.regression_detected.value:
            await self._trigger_recertification(
                envelope,
                trigger_reason="regression_detected",
            )
            return
        if envelope.event_type != AgentOpsEventType.retirement_trigger.value:
            return
        if self.agentops_service is None or not hasattr(
            self.agentops_service,
            "initiate_retirement_from_trigger",
        ):
            return

        payload = envelope.payload
        agent_fqn = payload.get("agent_fqn")
        workspace_id = payload.get("workspace_id")
        revision_id = payload.get("revision_id")
        if agent_fqn is None or workspace_id is None or revision_id is None:
            return
        await self.agentops_service.initiate_retirement_from_trigger(
            str(agent_fqn),
            UUID(str(revision_id)),
            UUID(str(workspace_id)),
            trigger_reason="sustained_degradation",
        )

    async def handle_trust_event(self, envelope: EventEnvelope) -> None:
        trigger_reason = {
            "trust.agent_revision_changed": "revision_changed",
            "trust.policy_changed": "policy_changed",
            "trust.certification_expiring": "expiry_approaching",
            "trust.conformance_failed": "conformance_failed",
        }.get(envelope.event_type)
        if trigger_reason is None:
            return
        await self._trigger_recertification(envelope, trigger_reason=trigger_reason)

    async def _current_target(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> dict[str, UUID] | None:
        if self.registry_service is None or not hasattr(
            self.registry_service,
            "list_active_agents",
        ):
            return None
        active_agents = await self.registry_service.list_active_agents(workspace_id)
        for item in active_agents:
            if item.get("agent_fqn") == agent_fqn and item.get("revision_id") is not None:
                return {
                    "revision_id": UUID(str(item["revision_id"])),
                }
        return None

    async def _materialize_baseline_if_ready(
        self,
        *,
        baseline: BehavioralBaseline,
        workspace_id: UUID,
    ) -> None:
        quality_samples = await self.detector.fetch_samples(
            revision_id=baseline.revision_id,
            agent_fqn=baseline.agent_fqn,
            workspace_id=workspace_id,
            dimension="quality",
            column="quality_score",
        )
        if len(quality_samples) < self.detector.minimum_sample_size:
            return

        latency_samples = await self.detector.fetch_samples(
            revision_id=baseline.revision_id,
            agent_fqn=baseline.agent_fqn,
            workspace_id=workspace_id,
            dimension="latency",
            column="execution_duration_ms",
        )
        cost_samples = await self.detector.fetch_samples(
            revision_id=baseline.revision_id,
            agent_fqn=baseline.agent_fqn,
            workspace_id=workspace_id,
            dimension="cost",
            column="cost_usd",
        )
        safety_samples = await self.detector.fetch_samples(
            revision_id=baseline.revision_id,
            agent_fqn=baseline.agent_fqn,
            workspace_id=workspace_id,
            dimension="safety",
            column="toFloat64(safety_passed)",
        )

        now = datetime.now(UTC)
        baseline.quality_mean = _mean(quality_samples)
        baseline.quality_stddev = _stddev(quality_samples)
        baseline.latency_p50_ms = _percentile(latency_samples, 50.0)
        baseline.latency_p95_ms = _percentile(latency_samples, 95.0)
        baseline.latency_stddev_ms = _stddev(latency_samples)
        baseline.error_rate_mean = 1.0 - _mean(safety_samples)
        baseline.cost_per_execution_mean = _mean(cost_samples)
        baseline.cost_per_execution_stddev = _stddev(cost_samples)
        baseline.safety_pass_rate = _mean(safety_samples)
        baseline.sample_size = len(quality_samples)
        baseline.baseline_window_end = now
        baseline.baseline_window_start = now - timedelta(days=30)
        baseline.status = BaselineStatus.ready

    async def _trigger_recertification(
        self,
        envelope: EventEnvelope,
        *,
        trigger_reason: str,
    ) -> None:
        if self.trust_service is None:
            return
        payload = envelope.payload
        agent_fqn = payload.get("agent_fqn") or payload.get("agent_id")
        revision_id = payload.get("revision_id") or payload.get("agent_revision_id")
        workspace_id = payload.get("workspace_id") or envelope.correlation_context.workspace_id
        if agent_fqn is None or revision_id is None or workspace_id is None:
            return
        dedupe_key = _event_key(envelope)
        if dedupe_key in self._seen_event_ids:
            return
        self._seen_event_ids.add(dedupe_key)
        await self.trust_service.trigger_recertification(
            str(agent_fqn),
            UUID(str(revision_id)),
            trigger_reason,
        )
        if self.governance_publisher is None:
            return
        await self.governance_publisher.record(
            AgentOpsEventType.recertification_triggered.value,
            str(agent_fqn),
            UUID(str(workspace_id)),
            payload={
                "trigger_reason": trigger_reason,
                "source_event_type": envelope.event_type,
                "event_id": payload.get("event_id"),
            },
            actor=None,
            revision_id=UUID(str(revision_id)),
        )

    async def _handle_ate_completion(self, envelope: EventEnvelope, *, passed: bool) -> None:
        if self.agentops_service is None:
            return
        handler = getattr(self.agentops_service, "_adaptation_pipeline", None)
        if not callable(handler):
            return
        ate_run_id = envelope.payload.get("ate_run_id")
        if ate_run_id is None:
            return
        pipeline = handler()
        await pipeline.handle_ate_result(UUID(str(ate_run_id)), passed=passed)


def register_agentops_governance_consumers(
    manager: EventConsumerManager,
    *,
    group_id: str,
    triggers: AgentOpsGovernanceTriggers,
) -> None:
    manager.subscribe(
        "evaluation.events",
        group_id,
        triggers.handle_evaluation_event,
    )
    manager.subscribe(
        "agentops.events",
        f"{group_id}-retirement",
        triggers.handle_agentops_event,
    )
    manager.subscribe(
        "trust.events",
        f"{group_id}-governance",
        triggers.handle_trust_event,
    )


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(np.mean(np.asarray(values, dtype=float)))


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return float(np.std(np.asarray(values, dtype=float), ddof=1))


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values, dtype=float), percentile))


def _event_key(envelope: EventEnvelope) -> str:
    event_id = envelope.payload.get("event_id")
    if event_id is not None:
        return str(event_id)
    return f"{envelope.event_type}:{envelope.correlation_context.correlation_id}"
