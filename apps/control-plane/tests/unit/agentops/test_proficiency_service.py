from __future__ import annotations

from platform.agentops.models import ProficiencyLevel
from platform.agentops.proficiency.service import ProficiencyService
from platform.context_engineering.models import ContextAssemblyRecord
from uuid import UUID, uuid4

import pytest
from tests.agentops_support import build_proficiency_assessment, utcnow
from tests.registry_support import ExecuteResultStub


class _SessionStub:
    def __init__(self, records):
        self.records = list(records)

    async def execute(self, statement):
        del statement
        return ExecuteResultStub(many=self.records)


class _RepositoryStub:
    def __init__(self, records, *, latest=None, history=None, fleet_items=None):
        self.session = _SessionStub(records)
        self.latest = latest
        self.history = list(history or [])
        self.fleet_items = list(fleet_items or [])
        self.created = None
        self.captured_levels = None

    async def create_proficiency_assessment(self, assessment):
        assessment.created_at = assessment.assessed_at
        assessment.updated_at = assessment.assessed_at
        self.created = assessment
        self.latest = assessment
        return assessment

    async def get_latest_proficiency_assessment(self, agent_fqn, workspace_id):
        del agent_fqn, workspace_id
        return self.latest

    async def list_proficiency_assessments(self, agent_fqn, workspace_id, *, cursor=None, limit=20):
        del agent_fqn, workspace_id, cursor, limit
        return self.history, None

    async def list_proficiency_fleet(self, workspace_id, *, levels=None):
        del workspace_id
        self.captured_levels = levels
        return list(self.fleet_items)


class _RegistryStub:
    def __init__(self, state):
        self.state = state

    async def get_profile_state(self, agent_fqn: str, workspace_id: UUID):
        del agent_fqn, workspace_id
        return self.state


def _record(
    workspace_id: UUID,
    *,
    agent_fqn: str = "finance:agent",
    quality_pre: float = 0.80,
    quality_post: float = 0.82,
    token_pre: int = 100,
    token_post: int = 102,
):
    item = ContextAssemblyRecord(
        id=uuid4(),
        workspace_id=workspace_id,
        execution_id=uuid4(),
        step_id=uuid4(),
        agent_fqn=agent_fqn,
        profile_id=None,
        quality_score_pre=quality_pre,
        quality_score_post=quality_post,
        token_count_pre=token_pre,
        token_count_post=token_post,
        sources_queried=["history"],
        sources_available=["history", "memory"],
        compaction_applied=False,
        compaction_actions=[],
        privacy_exclusions=[],
        provenance_chain=[],
        bundle_storage_key=None,
        ab_test_id=None,
        ab_test_group=None,
        flags=[],
    )
    item.created_at = utcnow()
    item.updated_at = item.created_at
    return item


@pytest.mark.asyncio
async def test_compute_for_agent_persists_weighted_level() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub(
        [
            _record(workspace_id, quality_pre=0.82, quality_post=0.84),
            _record(workspace_id, quality_pre=0.86, quality_post=0.88),
            _record(workspace_id, quality_pre=0.90, quality_post=0.92),
        ]
    )
    service = ProficiencyService(
        repository=repository,  # type: ignore[arg-type]
        registry_service=_RegistryStub({"status": "active"}),
        min_observations_per_dimension=2,
        dwell_time_hours=24,
    )

    response = await service.compute_for_agent("finance:agent", workspace_id, trigger="manual")

    assert response.level == ProficiencyLevel.expert
    assert response.observation_count == 9
    assert repository.created is not None
    assert response.dimension_values["aggregate_score"] > 0.75


@pytest.mark.asyncio
async def test_compute_for_agent_returns_undetermined_when_dimensions_are_sparse() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub([_record(workspace_id, quality_post=0.60)])
    service = ProficiencyService(
        repository=repository,  # type: ignore[arg-type]
        registry_service=_RegistryStub({"status": "active"}),
        min_observations_per_dimension=2,
        dwell_time_hours=24,
    )

    response = await service.compute_for_agent("finance:agent", workspace_id)

    assert response.level == ProficiencyLevel.undetermined
    assert set(response.missing_dimensions) == {
        "retrieval_accuracy",
        "instruction_adherence",
        "context_coherence",
    }


@pytest.mark.asyncio
async def test_compute_for_agent_respects_dwell_time_gate_and_returns_latest() -> None:
    workspace_id = uuid4()
    latest = build_proficiency_assessment(
        workspace_id=workspace_id,
        level=ProficiencyLevel.advanced,
        assessed_at=utcnow(),
    )
    repository = _RepositoryStub(
        [
            _record(workspace_id, quality_pre=0.40, quality_post=0.42),
            _record(workspace_id, quality_pre=0.45, quality_post=0.48),
            _record(workspace_id, quality_pre=0.50, quality_post=0.52),
        ],
        latest=latest,
    )
    service = ProficiencyService(
        repository=repository,  # type: ignore[arg-type]
        registry_service=_RegistryStub({"status": "active"}),
        min_observations_per_dimension=2,
        dwell_time_hours=24,
    )

    response = await service.compute_for_agent("finance:agent", workspace_id)

    assert response.level == ProficiencyLevel.advanced
    assert repository.created is None


@pytest.mark.asyncio
async def test_query_fleet_expands_level_threshold() -> None:
    workspace_id = uuid4()
    fleet_items = [
        build_proficiency_assessment(workspace_id=workspace_id, level=ProficiencyLevel.competent)
    ]
    repository = _RepositoryStub([], fleet_items=fleet_items)
    service = ProficiencyService(
        repository=repository,  # type: ignore[arg-type]
        registry_service=_RegistryStub({"status": "active"}),
        min_observations_per_dimension=2,
        dwell_time_hours=24,
    )

    response = await service.query_fleet(workspace_id, level_at_or_below="competent")

    assert repository.captured_levels == ["novice", "competent"]
    assert response.total == 1
