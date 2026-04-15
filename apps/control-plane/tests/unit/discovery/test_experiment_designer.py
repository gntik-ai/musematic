from __future__ import annotations

from datetime import UTC, datetime
from platform.common.clients.sandbox_manager import SandboxExecutionResult
from platform.common.config import PlatformSettings
from platform.discovery.exceptions import ExperimentNotApprovedError
from platform.discovery.experiment.designer import ExperimentDesigner, normalize_plan
from platform.discovery.models import DiscoveryExperiment, Hypothesis
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        id=uuid4(),
        workspace_id=uuid4(),
        session_id=uuid4(),
        title="h",
        description="d",
        reasoning="r",
        confidence=0.8,
        generating_agent_fqn="agent",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_design_approves_or_rejects_via_policy() -> None:
    hypothesis = _hypothesis()
    created: list[DiscoveryExperiment] = []
    repo = SimpleNamespace(
        create_experiment=AsyncMock(side_effect=lambda row: created.append(row) or row)
    )
    workflow = SimpleNamespace(
        create_execution=AsyncMock(return_value={"plan": {"code": "print(1)"}})
    )
    policy = SimpleNamespace(
        evaluate_conformance=AsyncMock(
            return_value={"passed": False, "violations": [{"rule_id": "r"}]}
        )
    )
    designer = ExperimentDesigner(
        repository=repo,
        publisher=SimpleNamespace(
            experiment_designed=AsyncMock(), experiment_completed=AsyncMock()
        ),
        settings=PlatformSettings(),
        workflow_service=workflow,
        policy_service=policy,
        sandbox_client=None,
        provenance_graph=SimpleNamespace(write_evidence=AsyncMock()),
        elo_engine=SimpleNamespace(apply_evidence_bonus=AsyncMock()),
    )

    experiment = await designer.design(hypothesis, actor_id=uuid4())

    assert experiment.governance_status == "rejected"
    assert experiment.governance_violations == [{"rule_id": "r"}]
    assert experiment.plan["code"] == "print(1)"


@pytest.mark.asyncio
async def test_execute_blocks_rejected_and_runs_approved_sandbox() -> None:
    hypothesis = _hypothesis()
    experiment = DiscoveryExperiment(
        id=uuid4(),
        workspace_id=hypothesis.workspace_id,
        session_id=hypothesis.session_id,
        hypothesis_id=hypothesis.id,
        plan={"code": "print('ok')"},
        governance_status="approved",
        governance_violations=[],
        execution_status="not_started",
        designed_by_agent_fqn="designer",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo = SimpleNamespace(
        update_experiment=AsyncMock(side_effect=lambda row, **values: _assign(row, values))
    )
    sandbox = SimpleNamespace(
        execute_code=AsyncMock(
            return_value=SandboxExecutionResult(
                execution_id="exec-1",
                status="completed",
                stdout="ok",
                stderr="",
                exit_code=0,
                artifacts=[],
            )
        )
    )
    graph = SimpleNamespace(write_evidence=AsyncMock())
    elo = SimpleNamespace(apply_evidence_bonus=AsyncMock())
    designer = ExperimentDesigner(
        repository=repo,
        publisher=SimpleNamespace(
            experiment_designed=AsyncMock(), experiment_completed=AsyncMock()
        ),
        settings=PlatformSettings(),
        workflow_service=None,
        policy_service=None,
        sandbox_client=sandbox,
        provenance_graph=graph,
        elo_engine=elo,
    )

    rejected = _assign(experiment, {"governance_status": "rejected"})
    with pytest.raises(ExperimentNotApprovedError):
        await designer.execute(rejected, hypothesis)
    experiment.governance_status = "approved"
    executed = await designer.execute(experiment, hypothesis)

    assert executed.execution_status == "completed"
    assert executed.results["stdout"] == "ok"
    graph.write_evidence.assert_awaited_once()
    elo.apply_evidence_bonus.assert_awaited_once()


def test_normalize_plan_adds_required_sections() -> None:
    hypothesis = _hypothesis()
    plan = normalize_plan({"objective": "custom"}, hypothesis)

    assert plan["objective"] == "custom"
    assert "success_criteria" in plan
    assert plan["code"]


@pytest.mark.asyncio
async def test_design_defaults_and_execute_without_sandbox() -> None:
    hypothesis = _hypothesis()
    repo = SimpleNamespace(
        create_experiment=AsyncMock(side_effect=lambda row: _assign(row, {"id": uuid4()})),
        update_experiment=AsyncMock(side_effect=lambda row, **values: _assign(row, values)),
    )
    publisher = SimpleNamespace(experiment_designed=AsyncMock(), experiment_completed=AsyncMock())
    designer = ExperimentDesigner(
        repository=repo,
        publisher=publisher,
        settings=PlatformSettings(),
        workflow_service=None,
        policy_service=SimpleNamespace(
            evaluate_conformance=AsyncMock(return_value=SimpleNamespace(passed=True, violations=[]))
        ),
        sandbox_client=None,
        provenance_graph=SimpleNamespace(write_evidence=AsyncMock()),
        elo_engine=SimpleNamespace(apply_evidence_bonus=AsyncMock()),
    )

    experiment = await designer.design(hypothesis, actor_id=uuid4())
    executed = await designer.execute(experiment, hypothesis)

    assert experiment.governance_status == "approved"
    assert executed.sandbox_execution_id.startswith("local-")
    publisher.experiment_designed.assert_awaited_once()
    publisher.experiment_completed.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_failed_and_timeout_results() -> None:
    hypothesis = _hypothesis()
    experiment = DiscoveryExperiment(
        id=uuid4(),
        workspace_id=hypothesis.workspace_id,
        session_id=hypothesis.session_id,
        hypothesis_id=hypothesis.id,
        plan={"code": "bad"},
        governance_status="approved",
        governance_violations=[],
        execution_status="not_started",
        designed_by_agent_fqn="designer",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo = SimpleNamespace(
        update_experiment=AsyncMock(side_effect=lambda row, **values: _assign(row, values))
    )
    sandbox = SimpleNamespace(
        execute_code=AsyncMock(
            side_effect=[
                SandboxExecutionResult("exec-fail", "completed", "", "bad", 2, []),
                SandboxExecutionResult("exec-timeout", "timeout", "", "timeout", None, []),
            ]
        )
    )
    designer = ExperimentDesigner(
        repository=repo,
        publisher=SimpleNamespace(
            experiment_designed=AsyncMock(), experiment_completed=AsyncMock()
        ),
        settings=PlatformSettings(),
        workflow_service=None,
        policy_service=None,
        sandbox_client=sandbox,
        provenance_graph=SimpleNamespace(write_evidence=AsyncMock()),
        elo_engine=SimpleNamespace(apply_evidence_bonus=AsyncMock()),
    )

    failed = await designer.execute(experiment, hypothesis)
    failed_status = failed.execution_status
    experiment.execution_status = "not_started"
    timed_out = await designer.execute(experiment, hypothesis)

    assert failed_status == "failed"
    assert timed_out.execution_status == "timeout"


def _assign(row, values):
    for key, value in values.items():
        setattr(row, key, value)
    return row
