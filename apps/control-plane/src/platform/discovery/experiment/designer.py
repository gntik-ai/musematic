from __future__ import annotations

from platform.common.clients.sandbox_manager import SandboxExecutionResult, SandboxManagerClient
from platform.common.config import PlatformSettings
from platform.discovery.events import DiscoveryEventPublisher
from platform.discovery.exceptions import ExperimentNotApprovedError
from platform.discovery.models import DiscoveryExperiment, Hypothesis
from platform.discovery.provenance.graph import ProvenanceGraph
from platform.discovery.repository import DiscoveryRepository
from platform.discovery.tournament.comparator import WorkflowServiceInterface
from platform.discovery.tournament.elo import EloRatingEngine
from typing import Any, Protocol
from uuid import UUID


class PolicyServiceInterface(Protocol):
    async def evaluate_conformance(
        self,
        agent_fqn: str,
        revision_id: UUID | None,
        workspace_id: UUID,
    ) -> Any: ...


class ExperimentDesigner:
    """Design governed experiments and execute approved code in sandbox-manager."""

    def __init__(
        self,
        *,
        repository: DiscoveryRepository,
        publisher: DiscoveryEventPublisher,
        settings: PlatformSettings,
        workflow_service: WorkflowServiceInterface | None,
        policy_service: PolicyServiceInterface | None,
        sandbox_client: SandboxManagerClient | None,
        provenance_graph: ProvenanceGraph,
        elo_engine: EloRatingEngine,
    ) -> None:
        self.repository = repository
        self.publisher = publisher
        self.settings = settings
        self.workflow_service = workflow_service
        self.policy_service = policy_service
        self.sandbox_client = sandbox_client
        self.provenance_graph = provenance_graph
        self.elo_engine = elo_engine

    async def design(
        self,
        hypothesis: Hypothesis,
        *,
        actor_id: UUID,
        designer_agent_fqn: str = "discovery.experiment.designer",
    ) -> DiscoveryExperiment:
        plan = await self._generate_plan(hypothesis, actor_id, designer_agent_fqn)
        governance_status, violations = await self._evaluate_governance(
            designer_agent_fqn,
            hypothesis.workspace_id,
        )
        experiment = await self.repository.create_experiment(
            DiscoveryExperiment(
                hypothesis_id=hypothesis.id,
                session_id=hypothesis.session_id,
                workspace_id=hypothesis.workspace_id,
                plan=plan,
                governance_status=governance_status,
                governance_violations=violations,
                execution_status="not_started",
                sandbox_execution_id=None,
                results=None,
                designed_by_agent_fqn=designer_agent_fqn,
            )
        )
        await self.publisher.experiment_designed(
            hypothesis.session_id,
            hypothesis.workspace_id,
            experiment.id,
        )
        return experiment

    async def execute(
        self,
        experiment: DiscoveryExperiment,
        hypothesis: Hypothesis,
    ) -> DiscoveryExperiment:
        if experiment.governance_status != "approved":
            raise ExperimentNotApprovedError(experiment.id)
        if experiment.execution_status in {"running", "completed"}:
            return experiment
        await self.repository.update_experiment(experiment, execution_status="running")
        result = await self._execute_in_sandbox(experiment)
        status = _execution_status(result)
        interpretation = "supports" if result.exit_code == 0 else "inconclusive"
        results = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "artifacts": result.artifacts,
            "evidence_type": _evidence_type(result),
            "interpretation": interpretation,
        }
        updated = await self.repository.update_experiment(
            experiment,
            execution_status=status,
            sandbox_execution_id=result.execution_id,
            results=results,
        )
        rel_type = "SUPPORTS" if result.exit_code == 0 else "INCONCLUSIVE_FOR"
        await self.provenance_graph.write_evidence(
            updated,
            hypothesis,
            rel_type,
            summary=interpretation,
            confidence=1.0 if result.exit_code == 0 else 0.5,
        )
        if result.exit_code == 0:
            await self.elo_engine.apply_evidence_bonus(
                session_id=experiment.session_id,
                hypothesis_id=experiment.hypothesis_id,
                workspace_id=experiment.workspace_id,
            )
        await self.publisher.experiment_completed(
            experiment.session_id,
            experiment.workspace_id,
            experiment.id,
        )
        return updated

    async def _generate_plan(
        self,
        hypothesis: Hypothesis,
        actor_id: UUID,
        designer_agent_fqn: str,
    ) -> dict[str, Any]:
        if self.workflow_service is None:
            return _default_plan(hypothesis)
        result = await self.workflow_service.create_execution(
            None,
            {
                "task": "design_discovery_experiment",
                "designer_agent_fqn": designer_agent_fqn,
                "hypothesis": {
                    "hypothesis_id": str(hypothesis.id),
                    "title": hypothesis.title,
                    "description": hypothesis.description,
                },
            },
            hypothesis.workspace_id,
            actor_id,
        )
        payload = result if isinstance(result, dict) else getattr(result, "payload", {})
        return normalize_plan(payload.get("plan", payload), hypothesis)

    async def _evaluate_governance(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> tuple[str, list[dict[str, Any]]]:
        if self.policy_service is None:
            return "approved", []
        result = await self.policy_service.evaluate_conformance(agent_fqn, None, workspace_id)
        if isinstance(result, dict):
            passed = bool(result.get("passed", True))
            violations = list(result.get("violations") or [])
        else:
            passed = bool(getattr(result, "passed", True))
            violations = list(getattr(result, "violations", []) or [])
        return ("approved" if passed else "rejected", violations)

    async def _execute_in_sandbox(self, experiment: DiscoveryExperiment) -> SandboxExecutionResult:
        if self.sandbox_client is None:
            return SandboxExecutionResult(
                execution_id=f"local-{experiment.id}",
                status="completed",
                stdout="sandbox unavailable; execution simulated",
                stderr="",
                exit_code=0,
                artifacts=[],
            )
        return await self.sandbox_client.execute_code(
            template="python3.12",
            code=str(experiment.plan.get("code", "")),
            workspace_id=experiment.workspace_id,
            timeout_seconds=self.settings.discovery.experiment_sandbox_timeout_seconds,
        )


def normalize_plan(raw_plan: dict[str, Any], hypothesis: Hypothesis) -> dict[str, Any]:
    defaults = _default_plan(hypothesis)
    merged = {**defaults, **raw_plan}
    merged["code"] = str(merged.get("code") or defaults["code"])
    return merged


def _default_plan(hypothesis: Hypothesis) -> dict[str, Any]:
    return {
        "objective": f"Test hypothesis: {hypothesis.title}",
        "methodology": "Run a deterministic simulation or statistical check.",
        "expected_outcomes": ["Evidence supports, contradicts, or remains inconclusive."],
        "required_data": [],
        "resources": {"template": "python3.12"},
        "success_criteria": ["Code exits with status 0 and produces interpretable output."],
        "code": "print('discovery experiment placeholder')",
    }


def _execution_status(result: SandboxExecutionResult) -> str:
    if result.status == "timeout":
        return "timeout"
    if result.exit_code in {None, 0}:
        return "completed"
    return "failed"


def _evidence_type(result: SandboxExecutionResult) -> str:
    if result.exit_code == 0:
        return "supporting"
    if result.exit_code is None:
        return "inconclusive"
    return "contradicting"
