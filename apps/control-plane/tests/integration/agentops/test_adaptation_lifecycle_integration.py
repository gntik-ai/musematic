from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.agentops.dependencies import get_agentops_service
from platform.agentops.router import router
from platform.agentops.schemas import (
    AdaptationApplyResponse,
    AdaptationLineageResponse,
    AdaptationOutcomeResponse,
    AdaptationProposalResponse,
    AdaptationRevokeResponse,
    AdaptationRollbackResponse,
)
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI


class _LifecycleRouterServiceStub:
    def __init__(self, workspace_id: UUID) -> None:
        now = datetime.now(UTC)
        self.workspace_id = workspace_id
        self.proposal = AdaptationProposalResponse(
            id=uuid4(),
            workspace_id=workspace_id,
            agent_fqn="finance:agent",
            revision_id=uuid4(),
            status="approved",
            proposal_details={"adjustments": [{"target": "context_profile"}]},
            signals=[{"rule_type": "quality_trend"}],
            expected_improvement={"metric": "quality_score", "target_delta": 0.1},
            pre_apply_snapshot_key=None,
            applied_at=None,
            applied_by=None,
            rolled_back_at=None,
            rolled_back_by=None,
            rollback_reason=None,
            expires_at=now + timedelta(days=7),
            revoked_at=None,
            revoked_by=None,
            revoke_reason=None,
            signal_source="manual",
            review_reason="looks good",
            reviewed_by=uuid4(),
            reviewed_at=now,
            candidate_revision_id=None,
            evaluation_run_id=None,
            completed_at=None,
            completion_note=None,
            created_at=now,
            updated_at=now,
        )
        self.outcome = AdaptationOutcomeResponse(
            id=uuid4(),
            proposal_id=self.proposal.id,
            observation_window_start=now - timedelta(hours=48),
            observation_window_end=now,
            expected_delta={"metric": "quality_score", "target_delta": 0.1},
            observed_delta={"metric": "quality_score", "observed_delta": 0.15},
            classification="improved",
            variance_annotation=None,
            measured_at=now,
            created_at=now,
            updated_at=now,
        )

    async def apply_adaptation(
        self, proposal_id: UUID, *, actor: UUID, reason: str | None = None
    ) -> AdaptationApplyResponse:
        assert proposal_id == self.proposal.id
        self.proposal.status = "applied"
        self.proposal.applied_by = actor
        self.proposal.applied_at = datetime.now(UTC)
        self.proposal.pre_apply_snapshot_key = "snapshot-1"
        self.proposal.completion_note = reason
        return AdaptationApplyResponse(
            proposal=self.proposal, pre_apply_configuration_hash="sha256:preapply"
        )

    async def rollback_adaptation(
        self, proposal_id: UUID, *, actor: UUID, reason: str
    ) -> AdaptationRollbackResponse:
        assert proposal_id == self.proposal.id
        self.proposal.status = "rolled_back"
        self.proposal.rolled_back_by = actor
        self.proposal.rollback_reason = reason
        self.proposal.rolled_back_at = datetime.now(UTC)
        return AdaptationRollbackResponse(proposal=self.proposal, byte_identical_to_pre_apply=True)

    async def revoke_adaptation_approval(
        self, proposal_id: UUID, *, reason: str, actor: UUID
    ) -> AdaptationRevokeResponse:
        assert proposal_id == self.proposal.id
        self.proposal.status = "proposed"
        self.proposal.revoked_by = actor
        self.proposal.revoke_reason = reason
        self.proposal.revoked_at = datetime.now(UTC)
        return AdaptationRevokeResponse(proposal=self.proposal)

    async def get_adaptation_outcome(self, proposal_id: UUID) -> AdaptationOutcomeResponse:
        assert proposal_id == self.proposal.id
        return self.outcome

    async def get_adaptation_lineage(self, proposal_id: UUID) -> AdaptationLineageResponse:
        assert proposal_id == self.proposal.id
        return AdaptationLineageResponse(
            proposal=self.proposal,
            snapshot={
                "pre_apply": {"id": "snapshot-1", "configuration_hash": "sha256:preapply"},
            },
            outcome=self.outcome,
        )


def _build_app(service: _LifecycleRouterServiceStub, workspace_id: UUID, actor_id: UUID) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(actor_id),
        "workspace_id": str(workspace_id),
    }
    app.dependency_overrides[get_agentops_service] = lambda: service
    return app


@pytest.mark.asyncio
async def test_apply_and_rollback_routes_return_extended_payloads() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _LifecycleRouterServiceStub(workspace_id)
    app = _build_app(service, workspace_id, actor_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        applied = await client.post(
            f"/api/v1/agentops/adaptations/{service.proposal.id}/apply", json={"reason": "ship"}
        )
        rolled_back = await client.post(
            f"/api/v1/agentops/adaptations/{service.proposal.id}/rollback", json={"reason": "undo"}
        )

    assert applied.status_code == 200
    assert applied.json()["proposal"]["status"] == "applied"
    assert applied.json()["pre_apply_configuration_hash"] == "sha256:preapply"
    assert rolled_back.status_code == 200
    assert rolled_back.json()["proposal"]["status"] == "rolled_back"
    assert rolled_back.json()["byte_identical_to_pre_apply"] is True


@pytest.mark.asyncio
async def test_revoke_outcome_and_lineage_routes_return_expected_shapes() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _LifecycleRouterServiceStub(workspace_id)
    app = _build_app(service, workspace_id, actor_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        revoked = await client.post(
            f"/api/v1/agentops/adaptations/{service.proposal.id}/revoke-approval",
            json={"reason": "hold"},
        )
        outcome = await client.get(f"/api/v1/agentops/adaptations/{service.proposal.id}/outcome")
        lineage = await client.get(f"/api/v1/agentops/adaptations/{service.proposal.id}/lineage")

    assert revoked.status_code == 200
    assert revoked.json()["proposal"]["status"] == "proposed"
    assert outcome.status_code == 200
    assert outcome.json()["classification"] == "improved"
    assert lineage.status_code == 200
    assert lineage.json()["snapshot"]["pre_apply"]["id"] == "snapshot-1"
