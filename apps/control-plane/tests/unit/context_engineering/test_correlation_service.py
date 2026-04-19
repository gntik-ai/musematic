from __future__ import annotations

from platform.context_engineering.correlation_service import CorrelationService
from platform.context_engineering.models import ContextAssemblyRecord, CorrelationResult
from uuid import uuid4

import pytest
from tests.agentops_support import utcnow
from tests.context_engineering_support import EventProducerStub
from tests.registry_support import ExecuteResultStub


class _SessionStub:
    def __init__(self, records):
        self.records = list(records)

    async def execute(self, statement):
        del statement
        return ExecuteResultStub(many=self.records)


class _RepositoryStub:
    def __init__(self, records, *, latest_rows=None, fleet_rows=None):
        self.session = _SessionStub(records)
        self.latest_rows = list(latest_rows or [])
        self.fleet_rows = list(fleet_rows or [])
        self.upserts = []

    async def upsert_correlation_result(self, result: CorrelationResult):
        result.created_at = result.computed_at
        result.updated_at = result.computed_at
        self.upserts.append(result)
        return result

    async def get_latest_by_agent(self, workspace_id, agent_fqn, *, window_days=None):
        del workspace_id, agent_fqn, window_days
        return list(self.latest_rows)

    async def list_fleet_by_classification(self, workspace_id, *, classification=None):
        del workspace_id, classification
        return list(self.fleet_rows)


def _record(
    workspace_id,
    *,
    agent_fqn="finance:agent",
    quality_pre=0.5,
    quality_post=0.5,
    token_pre=100,
    token_post=100,
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
async def test_compute_for_agent_emits_computed_and_strong_negative_events() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub(
        [
            _record(workspace_id, quality_pre=1.0, quality_post=0.2),
            _record(workspace_id, quality_pre=0.8, quality_post=0.4),
            _record(workspace_id, quality_pre=0.6, quality_post=0.6),
            _record(workspace_id, quality_pre=0.4, quality_post=0.8),
            _record(workspace_id, quality_pre=0.2, quality_post=1.0),
        ]
    )
    producer = EventProducerStub()
    service = CorrelationService(
        repository=repository,  # type: ignore[arg-type]
        event_producer=producer,
        min_data_points=3,
    )

    results = await service.compute_for_agent(workspace_id, "finance:agent", window_days=30)
    by_dimension = {item.dimension: item for item in results}

    assert len(results) == 3
    assert by_dimension["retrieval_accuracy"].classification == "strong_positive"
    assert by_dimension["instruction_adherence"].classification == "strong_negative"
    assert [item["event_type"] for item in producer.published].count(
        "context_engineering.correlation.computed"
    ) == 3
    assert [item["event_type"] for item in producer.published].count(
        "context_engineering.correlation.strong_negative"
    ) == 1


@pytest.mark.asyncio
async def test_compute_for_agent_is_inconclusive_below_minimum_sample_size() -> None:
    workspace_id = uuid4()
    repository = _RepositoryStub(
        [
            _record(workspace_id, quality_pre=0.8, quality_post=0.7),
            _record(workspace_id, quality_pre=0.7, quality_post=0.6),
        ]
    )
    service = CorrelationService(
        repository=repository,  # type: ignore[arg-type]
        event_producer=None,
        min_data_points=3,
    )

    results = await service.compute_for_agent(workspace_id, "finance:agent", window_days=30)

    assert {item.classification for item in results} == {"inconclusive"}
    assert all(item.coefficient is None for item in results)


@pytest.mark.asyncio
async def test_get_latest_and_query_fleet_wrap_repository_rows() -> None:
    workspace_id = uuid4()
    row = CorrelationResult(
        id=uuid4(),
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        dimension="retrieval_accuracy",
        performance_metric="quality_score",
        window_start=utcnow(),
        window_end=utcnow(),
        coefficient=0.9,
        classification="strong_positive",
        data_point_count=12,
        computed_at=utcnow(),
    )
    row.created_at = row.computed_at
    row.updated_at = row.computed_at
    repository = _RepositoryStub([], latest_rows=[row], fleet_rows=[row])
    service = CorrelationService(
        repository=repository,  # type: ignore[arg-type]
        event_producer=None,
        min_data_points=3,
    )

    latest = await service.get_latest(
        workspace_id, "finance:agent", classification="strong_positive"
    )
    fleet = await service.query_fleet(workspace_id, classification="strong_positive")

    assert latest.total == 1
    assert fleet.total == 1
    assert latest.items[0].dimension == "retrieval_accuracy"
