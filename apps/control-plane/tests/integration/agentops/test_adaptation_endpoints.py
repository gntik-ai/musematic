from __future__ import annotations

from datetime import UTC, datetime
from platform.agentops.dependencies import get_agentops_service
from platform.agentops.router import router
from platform.agentops.schemas import AdaptationProposalListResponse, AdaptationProposalResponse
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI


class _AdaptationRouterServiceStub:
    def __init__(self, workspace_id: UUID) -> None:
        self.workspace_id = workspace_id
        self.actor_id = uuid4()
        self.proposals: dict[UUID, AdaptationProposalResponse] = {}

    async def propose_adaptation(
        self,
        agent_fqn: str,
        payload,
        *,
        actor: UUID,
    ) -> AdaptationProposalResponse:
        assert payload.workspace_id == self.workspace_id
        now = datetime.now(UTC)
        proposal = AdaptationProposalResponse(
            id=uuid4(),
            workspace_id=self.workspace_id,
            agent_fqn=agent_fqn,
            revision_id=payload.revision_id,
            status="proposed",
            proposal_details={"adjustments": [{"target": "context_profile"}]},
            signals=[{"rule_type": "quality_trend"}],
            review_reason=None,
            reviewed_by=None,
            reviewed_at=None,
            candidate_revision_id=None,
            evaluation_run_id=None,
            completed_at=None,
            completion_note=None,
            created_at=now,
            updated_at=now,
        )
        self.proposals[proposal.id] = proposal
        return proposal

    async def review_adaptation(
        self,
        proposal_id: UUID,
        payload,
        *,
        actor: UUID,
    ) -> AdaptationProposalResponse:
        proposal = self.proposals[proposal_id]
        proposal.review_reason = payload.reason
        proposal.reviewed_by = actor
        proposal.reviewed_at = datetime.now(UTC)
        if payload.decision == "approved":
            proposal.status = "testing"
            proposal.candidate_revision_id = uuid4()
            proposal.evaluation_run_id = uuid4()
        else:
            proposal.status = "rejected"
        return proposal

    async def list_adaptations(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
        status: str | None = None,
    ) -> AdaptationProposalListResponse:
        del cursor, limit
        assert workspace_id == self.workspace_id
        items = [item for item in self.proposals.values() if item.agent_fqn == agent_fqn]
        if status is not None:
            items = [item for item in items if item.status == status]
        return AdaptationProposalListResponse(items=items, next_cursor=None)


def _build_app(
    service: _AdaptationRouterServiceStub,
    workspace_id: UUID,
    actor_id: UUID,
) -> FastAPI:
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
async def test_post_adapt_creates_proposal() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _AdaptationRouterServiceStub(workspace_id)
    app = _build_app(service, workspace_id, actor_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/agentops/finance:agent/adapt",
            json={"workspace_id": str(workspace_id), "revision_id": str(uuid4())},
        )

    assert response.status_code == 201
    assert response.json()["status"] == "proposed"


@pytest.mark.asyncio
async def test_post_adaptation_review_approved_transitions_to_testing() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _AdaptationRouterServiceStub(workspace_id)
    app = _build_app(service, workspace_id, actor_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/agentops/finance:agent/adapt",
            json={"workspace_id": str(workspace_id), "revision_id": str(uuid4())},
        )
        proposal_id = created.json()["id"]
        response = await client.post(
            f"/api/v1/agentops/adaptations/{proposal_id}/review",
            json={"decision": "approved", "reason": "Looks good"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "testing"


@pytest.mark.asyncio
async def test_post_adaptation_review_rejected_transitions_to_rejected() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _AdaptationRouterServiceStub(workspace_id)
    app = _build_app(service, workspace_id, actor_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/agentops/finance:agent/adapt",
            json={"workspace_id": str(workspace_id), "revision_id": str(uuid4())},
        )
        proposal_id = created.json()["id"]
        response = await client.post(
            f"/api/v1/agentops/adaptations/{proposal_id}/review",
            json={"decision": "rejected", "reason": "Not worth it"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_get_adaptation_history_returns_proposals() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = _AdaptationRouterServiceStub(workspace_id)
    app = _build_app(service, workspace_id, actor_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        await client.post(
            "/api/v1/agentops/finance:agent/adapt",
            json={"workspace_id": str(workspace_id), "revision_id": str(uuid4())},
        )
        response = await client.get("/api/v1/agentops/finance:agent/adaptation-history")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["agent_fqn"] == "finance:agent"
