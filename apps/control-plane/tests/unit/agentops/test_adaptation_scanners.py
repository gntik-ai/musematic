from __future__ import annotations

from datetime import timedelta
from platform.agentops.models import AdaptationProposalStatus
from platform.agentops.service import AgentOpsService
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from tests.agentops_support import (
    build_adaptation_outcome,
    build_adaptation_proposal,
    build_adaptation_snapshot,
    utcnow,
)


class _RepositoryStub:
    def __init__(self, *, ttl=None, orphaned=None, pending=None, expired_snapshots=None):
        self.ttl = list(ttl or [])
        self.orphaned = list(orphaned or [])
        self.pending = list(pending or [])
        self.expired_snapshots = list(expired_snapshots or [])
        self.updated = []
        self.deleted = []

    async def list_proposals_past_ttl(self, now):
        del now
        return list(self.ttl)

    async def list_orphaned_proposals(self):
        return list(self.orphaned)

    async def list_proposals_pending_outcome(self, before):
        del before
        return list(self.pending)

    async def list_snapshots_past_retention(self, now):
        del now
        return list(self.expired_snapshots)

    async def delete_snapshot(self, snapshot):
        self.deleted.append(snapshot)

    async def update_adaptation(self, proposal):
        self.updated.append(proposal)
        return proposal


@pytest.mark.asyncio
async def test_ttl_and_orphan_scanners_transition_and_emit_events() -> None:
    expired = build_adaptation_proposal(
        status=AdaptationProposalStatus.proposed, expires_at=utcnow() - timedelta(hours=1)
    )
    orphaned = build_adaptation_proposal(status=AdaptationProposalStatus.approved)
    repository = _RepositoryStub(ttl=[expired], orphaned=[orphaned])
    governance = SimpleNamespace(record=AsyncMock())
    registry = SimpleNamespace(get_profile_state=AsyncMock(return_value={"status": "archived"}))
    service = AgentOpsService(
        repository=repository,  # type: ignore[arg-type]
        event_publisher=SimpleNamespace(),
        governance_publisher=governance,  # type: ignore[arg-type]
        trust_service=None,
        eval_suite_service=None,
        policy_service=None,
        workflow_service=None,
        registry_service=registry,
        redis_client=None,
        clickhouse_client=None,
    )

    expired_items = await service.ttl_scanner_task()
    orphaned_items = await service.orphan_scanner_task()

    assert expired_items[0].status == AdaptationProposalStatus.expired
    assert orphaned_items[0].status == AdaptationProposalStatus.orphaned
    assert governance.record.await_count == 2


@pytest.mark.asyncio
async def test_outcome_measurer_and_snapshot_gc_delegate_to_children() -> None:
    pending = build_adaptation_proposal(
        status=AdaptationProposalStatus.applied, applied_at=utcnow() - timedelta(hours=72)
    )
    snapshot = build_adaptation_snapshot(
        proposal_id=pending.id, retention_expires_at=utcnow() - timedelta(minutes=1)
    )
    repository = _RepositoryStub(pending=[pending], expired_snapshots=[snapshot])
    service = AgentOpsService(
        repository=repository,  # type: ignore[arg-type]
        event_publisher=SimpleNamespace(),
        governance_publisher=None,
        trust_service=None,
        eval_suite_service=None,
        policy_service=None,
        workflow_service=None,
        registry_service=None,
        redis_client=None,
        clickhouse_client=None,
    )
    outcome = build_adaptation_outcome(proposal_id=pending.id)
    service._adaptation_outcome_service = lambda: SimpleNamespace(
        measure_for_proposal=AsyncMock(return_value=outcome)
    )

    measured = await service.outcome_measurer_task()
    removed = await service.snapshot_retention_gc_task()

    assert measured[0].proposal_id == pending.id
    assert removed == 1
    assert repository.deleted == [snapshot]


@pytest.mark.asyncio
async def test_signal_poll_emits_degraded_once_and_recovers() -> None:
    workspace_id = uuid4()
    proposal = build_adaptation_proposal(
        status=AdaptationProposalStatus.proposed, signal_source="automatic", revision_id=uuid4()
    )
    repository = _RepositoryStub()
    governance = SimpleNamespace(record=AsyncMock())
    registry = SimpleNamespace(
        list_active_agents=AsyncMock(
            return_value=[
                {
                    "agent_fqn": proposal.agent_fqn,
                    "workspace_id": workspace_id,
                    "revision_id": proposal.revision_id,
                }
            ]
        )
    )
    service = AgentOpsService(
        repository=repository,  # type: ignore[arg-type]
        event_publisher=SimpleNamespace(),
        governance_publisher=governance,  # type: ignore[arg-type]
        trust_service=None,
        eval_suite_service=None,
        policy_service=None,
        workflow_service=None,
        registry_service=registry,
        redis_client=None,
        clickhouse_client=None,
    )

    class _Analyzer:
        def __init__(self):
            self.is_degraded = True
            self.failure_threshold = 5

    analyzer = _Analyzer()
    failing_pipeline = SimpleNamespace(propose=AsyncMock(side_effect=RuntimeError("boom")))
    service._behavioral_analyzer = lambda: analyzer
    service._adaptation_pipeline = lambda: failing_pipeline

    assert await service.signal_poll_task(workspace_id=workspace_id) == []
    assert governance.record.await_count == 1
    assert await service.signal_poll_task(workspace_id=workspace_id) == []
    assert governance.record.await_count == 1

    analyzer.is_degraded = False
    service._adaptation_pipeline = lambda: SimpleNamespace(propose=AsyncMock(return_value=proposal))
    created = await service.signal_poll_task(workspace_id=workspace_id)

    assert len(created) == 1
    assert created[0].id == proposal.id
    assert service._ingestion_degraded_emitted is False


@pytest.mark.asyncio
async def test_signal_poll_and_proficiency_recomputer_cover_skip_paths() -> None:
    workspace_id = uuid4()
    service = AgentOpsService(
        repository=_RepositoryStub(),  # type: ignore[arg-type]
        event_publisher=SimpleNamespace(),
        governance_publisher=None,
        trust_service=None,
        eval_suite_service=None,
        policy_service=None,
        workflow_service=None,
        registry_service=None,
        redis_client=None,
        clickhouse_client=None,
    )

    assert await service.signal_poll_task(workspace_id=workspace_id) == []

    invalid_registry = SimpleNamespace(
        list_active_agents=AsyncMock(return_value=[{"agent_fqn": "finance:agent"}])
    )
    service.registry_service = invalid_registry
    service._proficiency_recomputer = lambda: SimpleNamespace(
        run=AsyncMock(return_value=[{"ok": True}])
    )

    assert await service.signal_poll_task(workspace_id=workspace_id) == []
    assert await service.proficiency_recomputer_task(workspace_id=workspace_id) == [{"ok": True}]
